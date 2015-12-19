'''A simple text editor for Sugar
Written mostly by Nate Theis
Some GTK code borrowed from Pippy
'''

from gettext import gettext as _

from gi.repository import Gtk
from gi.repository import Pango
import time
from gi.repository import GtkSource

from sugar3.activity import activity

from sugar3.graphics.toolbarbox import ToolbarBox
from sugar3.activity.widgets import ActivityToolbarButton, StopButton
from sugar3.graphics.toolbarbox import ToolbarButton

from sugar3.graphics import style
from sugar3.activity.widgets import EditToolbar

import mdnames

from groupthink import sugar_tools, gtk_tools


class EditActivity(sugar_tools.GroupActivity):
    '''A text editor for Sugar
    pylint says I need a docstring. Here you go.
    '''

    message_preparing = _("Loading...")
    message_joining = _("Joining shared activity...")
    message_loading = _("Reading journal entry...")

    def checkts(self):
        '''Check the timestamp
        If someone's modified our file in an external editor,
        we should reload the contents
        '''

        mtime = self.metadata[mdnames.sugartimestamp_md]
        etime = self.metadata[mdnames.cloudtimestamp_md]
        return mtime > etime

    def __init__(self, handle):
        '''We want to set up the buffer et al. early on
        sure there's early_setup, but that's not early enough
        '''

        self.buffer = GtkSource.Buffer()
        self.refresh_buffer = False

        self.text_view = GtkSource.View.new_with_buffer(self.buffer)
        self.scrollwindow = Gtk.ScrolledWindow()

        self.scrollwindow.add(self.text_view)

        sugar_tools.GroupActivity.__init__(self, handle)

    def fix_mimetype(self):
        '''We must have a mimetype. Sometimes, we don't (when we get launched
        newly.) This  fixes that.'''
        if self.metadata[mdnames.mimetype_md] == '':
            self.metadata[mdnames.mimetype_md] = "text/plain"
            #we MUST have a mimetype

    def setup_toolbar(self):
        '''Setup the top toolbar. Groupthink needs some work here.'''

        toolbox = ToolbarBox()

        activity_button = ActivityToolbarButton(self)
        toolbox.toolbar.insert(activity_button, 0)
        activity_button.show()

        self.set_toolbar_box(toolbox)
        toolbox.show()
        toolbar = toolbox.toolbar

        self.edit_toolbar = EditToolbar()
        edit_toolbar_button = ToolbarButton(
            page=self.edit_toolbar,
            icon_name='toolbar-edit')
        self.edit_toolbar.show()
        toolbar.insert(edit_toolbar_button, -1)
        edit_toolbar_button.show()

        self.edit_toolbar.undo.connect('clicked', self.undobutton_cb)
        self.edit_toolbar.redo.connect('clicked', self.redobutton_cb)
        self.edit_toolbar.copy.connect('clicked', self.copybutton_cb)
        self.edit_toolbar.paste.connect('clicked', self.pastebutton_cb)

        separator = Gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        toolbar.insert(separator, -1)
        separator.show()

        stop_button = StopButton(self)
        stop_button.props.accelerator = '<Ctrl>q'
        toolbox.toolbar.insert(stop_button, -1)
        stop_button.show()

    def initialize_display(self):
        '''Set up GTK and friends'''
        self.fix_mimetype()

        self.cloud.shared_buffer = gtk_tools.TextBufferSharePoint(self.buffer)

        self.setup_toolbar()
        #Some graphics code borrowed from Pippy

        lang_manager = GtkSource.LanguageManager.get_default()
        if hasattr(lang_manager, 'list_languages'):
            langs = lang_manager.list_languages()
        else:
            lang_ids = lang_manager.get_language_ids()
            langs = [lang_manager.get_language(lang_id) \
                         for lang_id in lang_ids]
            for lang in langs:
                for mtype in lang.get_mime_types():
                    if mtype == self.metadata[mdnames.mimetype_md]:
                        self.buffer.set_language(lang)
                        break

        self.text_view.set_editable(True)
        self.text_view.set_cursor_visible(True)

        if self.metadata[mdnames.mimetype_md] == "text/plain":
            self.text_view.set_show_line_numbers(False)
            self.text_view.set_wrap_mode(Gtk.WrapMode.WORD)
            font = Pango.FontDescription("Bitstream Vera Sans " +
                                         str(style.FONT_SIZE))
        else:
            if hasattr(self.buffer, 'set_highlight'):
                self.buffer.set_highlight(True)
            else:
                self.buffer.set_highlight_syntax(True)

            self.text_view.set_show_line_numbers(True)

            self.text_view.set_wrap_mode(Gtk.WrapMode.CHAR)
            self.text_view.set_insert_spaces_instead_of_tabs(True)
            self.text_view.set_tab_width(2)
            self.text_view.set_auto_indent(True)
            font = Pango.FontDescription("Monospace " +
                                         str(style.FONT_SIZE))

        self.text_view.modify_font(font)

        if self.refresh_buffer:
            #see load_from_journal()
            self.buffer.begin_not_undoable_action()
            self.buffer.set_text(self.refresh_buffer)
            self.buffer.end_not_undoable_action()

        self.text_view.show()

        #Return the main widget. our parents take care of GTK stuff
        return self.scrollwindow

    def save_to_journal(self, filename, cloudstring):
        '''Saves to the journal.
        We use metadata magic to keep the collab. stuff'''
        self.metadata[mdnames.cloudstring_md] = cloudstring

        #Also write to file:
        fhandle = open(filename, "w")

        bounds = self.buffer.get_bounds()
        text = self.buffer.get_text(bounds[0], bounds[1], True)

        fhandle.write(text)
        fhandle.close()

        self.fix_mimetype()

        #We can do full-text search on all Edit documents, yay
        self.metadata[mdnames.contents_md] = text

        #If we edit the file in another way, we need to reload the contents
        #we fudge the timestamp forwards by 5 seconds
        #mmmm, fudge
        self.metadata[mdnames.cloudtimestamp_md] = time.clock() + 5

    def load_from_journal(self, filename):
        '''Load the file. Duh.'''

        if mdnames.cloudstring_md in self.metadata:
            if self.checkts():
                #if we were edited in another program
                #we need to reload the text
                #setting self.refresh_buffer makes us do that
                text = open(filename, "r").read()  # yay hackish one-line read
                self.refresh_buffer = text

            #File has been saved with Edit, thus
            #load the fancy collaboration data
            #instead of just the text
            return self.metadata[mdnames.cloudstring_md]

        else:
            text = open(filename, "r").read()  # yay hackish one-line read

            self.buffer.set_text(text)
            return None

    def when_shared(self):
        self.edit_toolbar.undo.set_sensitive(False)
        self.edit_toolbar.redo.set_sensitive(False)

    def undobutton_cb(self, button):
        if self.buffer.can_undo():
            self.buffer.undo()

    def redobutton_cb(self, button):
        global text_buffer
        if self.buffer.can_redo():
            self.buffer.redo()

    def copybutton_cb(self, button):
        self.buffer.copy_clipboard(Gtk.Clipboard())

    def pastebutton_cb(self, button):
        self.buffer.paste_clipboard(Gtk.Clipboard(), None, True)
