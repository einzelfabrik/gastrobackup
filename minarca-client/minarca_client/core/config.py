# Copyright (C) 2021 IKUS Software inc. All rights reserved.
# IKUS Software inc. PROPRIETARY/CONFIDENTIAL.
# Use is subject to license terms.
'''
Created on Jun. 8, 2021

@author: Patrik Dufresne <patrik@ikus-soft.com>
'''
from collections import namedtuple
from functools import total_ordering
from gettext import gettext as _
from minarca_client.core.compat import (IS_LINUX, IS_MAC, IS_WINDOWS, get_home,
                                        get_temp)
import datetime
import javaproperties
import os
import re
import time


@total_ordering
class Datetime():
    """
    Friendly class to manipulate date in configuration file.
    """

    def __init__(self, epoch_ms=None):
        if epoch_ms is None:
            epoch_ms = int(time.time() * 1000)
        self.epoch_ms = int(epoch_ms)

    def __str__(self):
        return time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime(self.epoch_ms / 1000))

    def __repr__(self):
        return 'Datetime(%s)' % self.epoch_ms

    def __int__(self):
        return self.epoch_ms

    def __eq__(self, other):
        return hasattr(other, 'epoch_ms') and self.epoch_ms == other.epoch_ms

    def __lt__(self, other):
        return self.epoch_ms < other.epoch_ms

    def __sub__(self, other):
        return datetime.timedelta(milliseconds=self.epoch_ms - other.epoch_ms)


class Status(dict):
    """
    Used to persists backup status.
    """
    LAST_RESULTS = ['SUCCESS', 'FAILURE',
                    'UNKNOWN', 'RUNNING', 'STALE', 'INTERRUPT']
    _DEFAULT = {
        'details': None,
        'lastdate': None,
        'lastresult': 'UNKNOWN',
        'lastsuccess': None,
        'pid': None
    }

    def __init__(self, filename):
        assert filename
        self.filename = filename
        self._load()

    def save(self):
        values = {k: str(int(v)) if k in ['lastdate', 'lastsuccess'] else str(v)
                  for k, v in self.items()
                  if v is not None}
        with open(self.filename, 'w', encoding='latin-1') as f:
            return javaproperties.dump(values, f)

    def _load(self):
        self.clear()
        self.update(self._DEFAULT)
        if not os.path.exists(self.filename):
            return
        with open(self.filename, 'r', encoding='latin-1') as f:
            self.update(javaproperties.load(f))
            # Convert date from epoch in milliseconds
            for field in ['lastdate', 'lastsuccess']:
                if self[field]:
                    try:
                        self[field] = Datetime(self[field])
                    except (ValueError, KeyError):
                        self[field] = None


class Settings(dict):
    """
    Used to store minarca settings in `minarca.properties`
    """

    DAILY = 24
    HOURLY = 1
    WEEKLY = 168
    MONTHLY = 720

    _DEFAULT = {
        'username': None,
        'repositoryname': None,
        'remotehost': None,
        'remoteurl': None,
        'schedule': DAILY,
        'configured': False,
    }

    def __init__(self, filename):
        assert filename
        self.filename = filename
        self._load()

    def save(self):
        with open(self.filename, 'w', encoding='latin-1') as f:
            return javaproperties.dump({k: str(v) for k, v in self.items()}, f)

    def _load(self):
        self.clear()
        self.update(self._DEFAULT)
        if not os.path.exists(self.filename):
            return
        with open(self.filename, 'r', encoding='latin-1') as f:
            self.update(javaproperties.load(f))
            # schedule is an integer
            try:
                self['schedule'] = int(self['schedule'])
            except (ValueError, KeyError):
                self['schedule'] = self._DEFAULT.get('schedule')
            # configured is boolean
            try:
                self['configured'] = self['configured'] in [
                    'true', 'True', '1']
            except KeyError:
                self['configured'] = self._DEFAULT.get('configured')


class InvalidPatternError(Exception):
    """
    Raised when a pattern file contains an invalid line.
    """
    pass


Pattern = namedtuple('Pattern', ['include', 'pattern', 'comment'])
Pattern.is_wildcard = lambda self: '*' in self.pattern or '?' in self.pattern


class Patterns(list):

    def __init__(self, filename):
        assert filename
        self.filename = filename
        self._load()

    def _load(self):
        self.clear()
        if not os.path.exists(self.filename):
            return
        with open(self.filename, 'r', encoding='utf-8') as f:
            comment = None
            for line in f.readlines():
                line = line.rstrip()
                # Skip comment
                if line.startswith("#"):
                    comment = line[1:].strip()
                    continue
                if line[0] not in ['+', '-']:
                    raise InvalidPatternError(line)
                include = line[0] == '+'
                self.append(Pattern(include, line[1:], comment))
                comment = None

    def defaults(self):
        """
        Restore defaults patterns.
        """
        self.clear()
        self.extend([
            Pattern(True, os.path.join(get_home(), 'Documents'), _("User's Documents")),
        ])

        if IS_WINDOWS:
            self.extend([
                Pattern(False, "**/Thumbs.db", _("Thumbnails cache")),
                Pattern(False, "C:/pagefile.sys", _("Swap file")),
                Pattern(False, "C:/Recovery/", _("System Recovery")),
                Pattern(False, "C:/$Recycle.Bin/", _("Recycle bin")),
                Pattern(False, get_temp(), _("Temporary Folder")),
                Pattern(False, "**/*.bak", _("AutoCAD backup files")),
                Pattern(False, "**/~$*", _("Office temporary files")),
            ])
        if IS_MAC:
            self.extend([
            ])
        if IS_LINUX:
            self.extend([
                Pattern(False, "/dev", _("dev filesystem")),
                Pattern(False, "/proc", _("proc filesystem")),
                Pattern(False, "/sys", _("sys filesystem")),
                Pattern(False, "/tmp", _("Temporary Folder")),
                Pattern(False, "/run", _("Volatile program files")),
                Pattern(False, "/mnt", _("Mounted filesystems")),
                Pattern(False, "/media", _("External media")),
                Pattern(False, "**/lost+found", _("Ext4 Lost and Found")),
                Pattern(False, "**/.~*", _("Hidden temporary files")),
                Pattern(False, "**/*~", _("Vim Temporary files")),
            ])

    def save(self):
        with open(self.filename, 'w', encoding='utf-8') as f:
            self.write(f)

    def write(self, f):
        assert f
        assert hasattr(f, 'write')
        for pattern in self:
            # Write comments if any
            if pattern.comment:
                f.write("# %s\n" % pattern.comment.strip())
            # Write patterns
            f.write(('+%s\n' if pattern.include else '-%s\n') %
                    pattern.pattern)

    def group_by_roots(self):
        """
        Return the list of patterns for each root. On linux, we have a single root. On Windows,
        we might have multiple if the computer has multiple disk, like C:, D:, etc.
        """
        if IS_WINDOWS:
            # Find list of drives from patterns
            drives = list()
            for p in self:
                m = re.match('^[A-Z]:(\\\\|/)', p.pattern)
                if p.include and m:
                    drive = m.group(0).replace('\\', '/')
                    if drive not in drives:
                        drives.append(drive)
            for drive in drives:
                sublist = []
                for p in self:
                    m = re.match('^[A-Z]:(\\\\|/)', p.pattern)
                    if m and not p.pattern.replace('\\', '/').startswith(drive):
                        continue
                    sublist.append(
                        Pattern(p.include, p.pattern.replace('\\', '/'), None))
                yield (drive, sublist)
        elif len(self) > 0:
            yield ('/', self)