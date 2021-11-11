# Copyright (C) 2021 IKUS Software inc. All rights reserved.
# IKUS Software inc. PROPRIETARY/CONFIDENTIAL.
# Use is subject to license terms.
import logging
import threading
import tkinter
import tkinter.filedialog
import tkinter.simpledialog
import webbrowser

import pkg_resources
from minarca_client.core import Backup, RunningError
from minarca_client.locale import _
from minarca_client.ui import tkvue

logger = logging.getLogger(__name__)


class StatusView(tkvue.Component):
    template = pkg_resources.resource_string('minarca_client.ui', 'templates/status.html')

    def __init__(self, *args, **kwargs):
        self.backup = Backup()
        self.data = tkvue.Context({
            'lastresult': self.backup.get_status('lastresult'),
            'lastdate': self.backup.get_status('lastdate'),
            'details': self.backup.get_status('details'),
            'remoteurl': self.backup.get_settings('remoteurl'),
            'username': self.backup.get_settings('username'),
            'remotehost': self.backup.get_settings('remotehost'),
            'repositoryname': self.backup.get_settings('repositoryname'),
            # Computed variables
            'header_text': self.header_text,
            'header_text_style': self.header_text_style,
            'header_image_path': self.header_image_path,
            'start_stop_text': self.start_stop_text,
            'last_backup_text': self.last_backup_text,
            'remote_text_tooltip': self.remote_text_tooltip,
        })
        super().__init__(*args, **kwargs)
        # Start a background thread to update the status.
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._watch_status, daemon=True)
        self._thread.start()
        self.root.bind('<Destroy>', self.finalize)

    def finalize(self, event):
        """
        Called when window get destroyed.
        """
        self._stop_event.set()
        self._thread.join()

    @tkvue.computed
    def header_text(self, context):
        """
        Return a human description of backup health base on configuration and last result.
        """
        lastresult = context.lastresult
        if lastresult == 'SUCCESS':
            return _('Backup is healthy')
        elif lastresult == 'FAILURE':
            return _('Backup failed')
        elif lastresult == 'RUNNING':
            return _('Backup in progress')
        elif lastresult == 'STALE':
            return _('Backup is stale')
        elif lastresult == 'INTERRUPT':
            return _('Backup was interrupted')
        elif lastresult == 'UNKNOWN':
            return _('No backup yet')
        else:
            return _('Backup is not healthy')

    @tkvue.computed
    def header_text_style(self, context):
        lastresult = context.lastresult
        if lastresult in ['SUCCESS', 'RUNNING']:
            return 'H1.success.TLabel'
        elif lastresult in ['UNKNOWN', 'INTERRUPT']:
            return 'H1.info.TLabel'
        # Default
        return 'H1.danger.TLabel'

    @tkvue.computed
    def header_image_path(self, context):
        lastresult = context.lastresult
        if lastresult == 'SUCCESS':
            return 'success-24'
        elif lastresult == 'RUNNING':
            return 'spinner-24'
        elif lastresult in ['UNKNOWN', 'INTERRUPT']:
            return 'info-24'
        # Default
        return 'error-24'

    @tkvue.computed
    def last_backup_text(self, context):
        lastresult = context['lastresult']
        lastdate = context['lastdate']
        details = context['details']
        if lastresult == 'SUCCESS':
            return _('Complete successfully on %s. No background jobs using system resources.') % lastdate
        elif lastresult == 'FAILURE':
            return _('Last backup failed on %s for the following reason: %s\nNo background jobs using system resources.') % (lastdate, details)
        elif lastresult == 'RUNNING':
            return _('Backup is currently running in background and using system resources.')
        elif lastresult == 'STALE':
            return _('Was started in background on %s, but is currently stale an may use system resources.') % lastdate
        elif lastresult == 'INTERRUPT':
            return _('Was interrupted on %s. May be caused by loss of connection, computer standby or manual interruption.\nNo background jobs using system resources.') % lastdate
        elif lastresult == 'UNKNOWN':
            return _('Initial backup need to be started. You may take time to configure your parameters and start your initial backup manually.\nNo background jobs using system resources.')
        else:
            'unknown'

    @tkvue.computed
    def remote_text_tooltip(self, context):
        username = context['username']
        remotehost = context['remotehost']
        repositoryname = context['repositoryname']
        return '%s @ %s::%s' % (username, remotehost, repositoryname)

    @tkvue.computed
    def start_stop_text(self, context):
        lastresult = context['lastresult']
        if lastresult in ['RUNNING', 'STALE']:
            return _('Stop backup')
        return _('Start backup')

    def unlink(self):
        """
        Called to un register this agent from minarca server.
        """
        return_code = tkinter.messagebox.askyesno(
            parent=self.root,
            title=_('Are you sure ?'),
            message=_('Are you sure you want to disconnect this Minarca agent ?'),
            detail=_('If you disconnect this computer, this Minarca agent will erase its identity and will no longer run backup on schedule.'))
        if not return_code:
            # Operation cancel by user.
            return
        self.backup.unlink()
        self.root.winfo_toplevel().destroy()

    def browse_remote(self):
        """
        Open web browser.
        """
        remote_url = self.backup.get_remote_url()
        webbrowser.open(remote_url)

    def _watch_status(self):
        """
        Used to watch the status file and trigger an update whenever the status changes.
        """
        last_status = self.backup.get_status()
        while not self._stop_event.wait(timeout=.5):
            status = self.backup.get_status()
            if last_status != status:
                self.data['lastresult'] = status['lastresult']
                self.data['lastdate'] = status['lastdate']
                self.data['details'] = status['details']

    def start_stop_backup(self):
        try:
            self.backup.start(force=True, fork=True)
        except RunningError:
            self.backup.stop()
        except Exception:
            logger.exception('fail to start backup')
            tkinter.messagebox.showerror(
                parent=self.root,
                title=_("Fail to start backup !"),
                message=_("Fail to start backup !"),
                detail=_("A fatal error occurred when trying to start the backup process. This usually indicate a problem with the installation. Try re-installing Minarca Backup."))