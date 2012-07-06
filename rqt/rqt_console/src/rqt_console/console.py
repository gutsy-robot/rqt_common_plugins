import os
import new
import roslib, rospy
roslib.load_manifest('rqt_console')

from qt_gui.plugin import Plugin
from qt_gui.qt_binding_helper import loadUi
from QtGui import QApplication, QDialog, QHeaderView, QInputDialog, QMenu, QMessageBox, QTableView, QWidget, QFileDialog
from QtCore import qDebug, Qt, QTimer, Slot, QEvent

from message_data_model import MessageDataModel
from custom_widgets import MainWindow, SetupDialog, TimeDialog, ComboDialog

class Console(Plugin):
    def __init__(self, context):
        super(Console, self).__init__(context)
        # give QObjects reasonable names
        self.setObjectName('Console')

        # create QWidget
        self._mainwindow = MainWindow()
        # get path to UI file which is a sibling of this file
        ui_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'console.ui')
        # extend the widget with all attributes and children from UI file
        loadUi(ui_file, self._mainwindow)
        # give QObjects reasonable names
        self._mainwindow.setObjectName('ConsoleUi')
        # add widget to the user interface
        context.add_widget(self._mainwindow)
        self._datamodel = MessageDataModel()
        self._mainwindow.table_view.setModel(self._datamodel)

        self._mainwindow.table_view.setVisible(False)
        self._columnwidth = (600, 140, 200, 360, 200, 600)
        for idx, width in enumerate(self._columnwidth):
            self._mainwindow.table_view.horizontalHeader().resizeSection(idx, width)

        self._mainwindow.table_view.setVisible(True)

        self._mainwindow.table_view.mouseDoubleClickEvent = self.doubleclick_handler
        self._mainwindow.table_view.mousePressEvent = self.mouse_press_handler
        self._mainwindow.table_view.keyPressEvent = self.custom_keypress
        self._mainwindow.keyPressEvent = self.custom_keypress

        self._setupdialog = SetupDialog(context, self.message_callback)
        self._timedialog = TimeDialog()

    def show_filter_input(self, pos):
        columnclicked = self._mainwindow.table_view.columnAt(pos.x())
        if columnclicked == 0:
            text, ok = QInputDialog.getText(QWidget(), 'Message filter', 'Enter text (leave blank for no filtering):')
        elif columnclicked == 1:
            dlg = ComboDialog('Severity filter', 'Include only:',['All', 'Debug', 'Info', 'Warning', 'Error', 'Fatal'])
            ok = dlg.exec_()
            ok = (ok == 1)
            text = dlg.combo_box.currentText()

            #text, ok = QInputDialog.getItem(QWidget(), 'Severity filter', 'Include only:', ['All', 'Debug', 'Info', 'Warning', 'Error', 'Fatal'], 0, False)
        elif columnclicked == 2:
            text, ok = QInputDialog.getItem(QWidget(), 'Node filter', 'Include only:', ['All'] + self._datamodel.get_unique_col_data(columnclicked), 0, False)
        elif columnclicked == 3:
            self._clear_filter = False
            def handle_ignore():
                self._clear_filter = True
            self._timedialog.ignore_button_clicked.connect(handle_ignore)
            
            indexes = self._mainwindow.table_view.selectionModel().selectedIndexes()
            if len(indexes) == 0:
                self._timedialog.set_time()
            else:
            #get the current selection get the min and max times from this range
            #and set them as the min/max
                rowlist = []
                for current in indexes:
                    rowlist.append(current.row())
                rowlist = list(set(rowlist))
                rowlist.sort()
                
                mintime = self._datamodel.get_data(rowlist[0],3)
                maxtime = self._datamodel.get_data(rowlist[-1],3)
                mintime = mintime[:mintime.find('.')]
                maxtime = maxtime[:maxtime.find('.')]
                self._timedialog.set_time(int(mintime),int(maxtime))
            ok = self._timedialog.exec_()
            self._timedialog.ignore_button_clicked.disconnect(handle_ignore)
            ok = (ok == 1)
            if self._clear_filter:
                text = ''
            else:
                text = str(self._timedialog.min_dateedit.dateTime().toTime_t()) + ':' + str(self._timedialog.max_dateedit.dateTime().toTime_t())
        elif columnclicked == 4:
            unique_list = set()
            for topiclists in self._datamodel.get_unique_col_data(columnclicked):
                for item in topiclists.split(','):
                    unique_list.add(item.strip())
            unique_list = list(unique_list)
            text, ok = QInputDialog.getItem(QWidget(), 'Topic filter', 'Include only:', ['All'] + unique_list , 0, False)
        elif columnclicked == 5:
            text, ok = QInputDialog.getText(QWidget(), 'Location Filter', 'Enter text (leave blank for no filtering:')
        else:
            ok = False
        if ok:
            if text == 'All':
                text = ''
            self._datamodel.set_filter(columnclicked, text)
            self.reset_status()

    def process_inc_exc(self, col, exclude=False):
        prevfilter = self._datamodel.get_filter(col)
        if prevfilter != '':
            prevfilter = '(' + prevfilter + ')' + self._datamodel.get_and()
        num_selected = len(self._mainwindow.table_view.selectionModel().selectedIndexes())/6
        nodetext = ''
        for index in range(num_selected):
            addtext = self._mainwindow.table_view.selectionModel().selectedIndexes()[num_selected*col+index].data()
            if nodetext.find(addtext) == -1:
                if exclude:
                    addtext = self._datamodel.get_not() + addtext
                nodetext += addtext
                if exclude:
                    nodetext += self._datamodel.get_and()
                else:
                    nodetext += self._datamodel.get_or()
        nodetext = nodetext[:-1]
        newfilter = prevfilter + nodetext
        if prevfilter.find(nodetext) == -1:
            self._datamodel.set_filter(col,newfilter)

    def rightclick_menu(self, event):
        # menutext string entries are added as menu items
        # list entries are added as submenues with the second element as subitems
        menutext = []
        menutext.append('Edit Filter')
        if len(self._mainwindow.table_view.selectionModel().selectedIndexes()) != 0:
            menutext.append(['Exclude',['Node(s)','Message(s)']])
            menutext.append(['Include',['Node(s)','Message(s)']])
        menutext.append('Clear Filter')
        menutext.append('Copy')
        menutext.append('Save to File')
        menutext.append('Load from File')

        
        actions = []
        menu = QMenu()
        submenus = []
        submenuindex = -1
        for index, item in enumerate(menutext):
            if isinstance(item, basestring):
                actions.append((item, menu.addAction(item)))
            else:
                submenus.append(QMenu())
                for subitem in item[1]:
                    actions.append((item[0] + '>' + subitem, submenus[-1].addAction(subitem)))
                submenus[-1].setTitle(item[0])
                menu.addMenu(submenus[-1])
                                
        actions = dict(actions)
        action = menu.exec_(event.globalPos())

        #actions are accessed by dict index menutext>submenutext
        columnclicked = self._mainwindow.table_view.columnAt(event.pos().x())
        if action is None or action == 0:
            return 
        elif action == actions['Clear Filter']:
            self._datamodel.set_filter(columnclicked,'')
        elif action == actions['Edit Filter']:
            self.show_filter_input(event.pos())
        elif action == actions['Copy']:
            copytext = self._datamodel.get_selected_text(self._mainwindow.table_view.selectionModel().selectedIndexes())
            if copytext is not None:
                clipboard = QApplication.clipboard()
                clipboard.setText(copytext)
        elif action == actions['Save to File']:
            filename = QFileDialog.getOpenFileName(self._mainwindow, 'Save to File', '.')
            if filename[0] != '':
                fileHandle = open(filename[0], 'w')
                self._datamodel.save_to_file(fileHandle)
                fileHandle.close()
        elif action == actions['Load from File']:
            filename = QFileDialog.getOpenFileName(self._mainwindow, 'Load File', '.')
            if filename[0] != '':
                fileHandle = open(filename[0])
                self._datamodel.load_from_file(fileHandle)
                fileHandle.close()
        elif action == actions['Include>Node(s)']:
            self.process_inc_exc(2)
        elif action == actions['Include>Message(s)']:
            self.process_inc_exc(0)
        elif action == actions['Exclude>Node(s)']:
            self.process_inc_exc(2,True)
        elif action == actions['Exclude>Message(s)']:
            self.process_inc_exc(0,True)
        else:
            raise

    def message_callback(self, data):
        if self._mainwindow.logging_checkbox.isChecked():
            self._datamodel.insertRows(data)
            self.reset_status()
            self._mainwindow.table_view.reset()
    
    def mouse_press_handler(self, event,
                                  old_pressEvent=QTableView.mousePressEvent):
        if event.buttons()&Qt.RightButton and event.modifiers() == Qt.NoModifier:
            self.rightclick_menu(event)
            return event.accept()
        return old_pressEvent(self._mainwindow.table_view, event)
        
    def doubleclick_handler(self, event, old_clickEvent=QTableView.mouseDoubleClickEvent):
        return old_clickEvent(self._mainwindow.table_view, event)

    def custom_keypress(self, event, old_keyPressEvent=QTableView.keyPressEvent):
        if event.key() == Qt.Key_Delete:
            delete = QMessageBox.Yes
            if len(self._mainwindow.table_view.selectionModel().selectedIndexes()) == 0:
                delete = QMessageBox.question(self._mainwindow, 'Message', "Are you sure you want to delete all messages?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if delete == QMessageBox.Yes and event.key() == Qt.Key_Delete and event.modifiers() == Qt.NoModifier:
                if self._datamodel.remove_rows(self._mainwindow.table_view.selectionModel().selectedIndexes()):
                    self.reset_status()
                    return event.accept()
        return old_keyPressEvent(self._mainwindow.table_view, event)

    def shutdown_plugin(self):
        self._setupdialog.unsub_topic()
        self._setupdialog.close()

    def save_settings(self, plugin_settings, instance_settings):
        for index, member in enumerate(self._datamodel.message_members()):
            instance_settings.set_value(member,self._datamodel.get_filter(index))

    def restore_settings(self, plugin_settings, instance_settings):
        for index, member in enumerate(self._datamodel.message_members()):
            text = instance_settings.value(member)
            if type(text) is type(None):
                text=''
            self._datamodel.set_filter(index, text)

    def trigger_configuration(self):
        self._setupdialog.refresh_nodes()
        self._setupdialog.show()
        self._setupdialog.node_list.item(0).setSelected(True)
        self._setupdialog.node_changed(0)

    def reset_status(self):
        if self._datamodel.count() == self._datamodel.count(True):
            tip = self._mainwindow.tr('Displaying %s Messages' % (self._datamodel.count())) 
        else:
            tip = self._mainwindow.tr('Displaying %s of %s Messages' % (self._datamodel.count(True),self._datamodel.count())) 
        self._mainwindow.setStatusTip(tip)

