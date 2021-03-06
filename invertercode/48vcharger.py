import threading
# import paho.mqtt.client as mqtt
import sys
# sys.path.append(r'/home/pi/pysrc')
# sys.setrecursionlimit(200000)
# import pydevd
# pydevd.settrace('192.168.1.145')
import time
import serial
from __builtin__ import str
import toml
import os.path
import re

config_path = os.path.join((os.path.split(os.path.split(sys.argv[0])[0])[0]),
                           'config/48vcharger.toml')
with open(config_path) as f:
    config = toml.load(f, _dict=dict)
print config_path
# print config['uarts']
for key, value in config['uarts'].items():
    print key + ' = ' + value['dev']


class handle_control(threading.Thread):
    def __init__(self, threadID):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.command_list = []
        self.phy_list = {}
        self.init_handle_uart()

    def command(self, command_name, value=None):
        command = {'command': command_name,
                   'value': value,
                   'complete': {},
                   'reply': {}}
        self.command_list.append(command)

    def check_command_reply(self):
        done = None
        for v in reversed(self.command_list):
            for c in v['complete']:
                if v['complete'][c] is True and (done is True or done is None):
                    done = True
                else:
                    done = False
            if done is True:
                value = v
                self.command_list.remove(v)
                return value

    def get_command(self):
        return self.command_list

    def init_handle_uart(self):
        print 'init control'
        self.handle_uart_t = {}
        for key, value in config['uarts'].items():
            if value['phy'] not in self.phy_list:
                self.phy_list[value['phy']] = True
            handle_uart_t = handle_uart(self, key, value)
            self.handle_uart_t[key] = handle_uart_t
            self.handle_uart_t[key].daemon = True
            self.handle_uart_t[key].start()

    def run(self):
        print self.phy_list
        self.command('set_voltage', 24)
        while True:
            value = self.check_command_reply()
            print 'run control ' + str(value)
            time.sleep(1)


class handle_uart(threading.Thread):
    def __init__(self, control, threadID, value):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.control = control
        self.dev = value['dev']
        self.address = config['address']['control']
        print 'init ' + self.dev
        self.ser = serial.Serial(self.dev, baudrate=4800, bytesize=8,
                                 parity='N', stopbits=1, timeout=0)
        self.busy = False

    def run(self):
        while True:
            print self.dev + ' check for command'
            for v in self.control.command_list:
                if self.dev not in v['complete']:
                    v['complete'][self.dev] = False
                    print (self.dev + ' run command = ' + str(v['command'])
                           + ', ' + str(v['value']))
                    v['reply'][self.dev] = self.send_command(v['command'],
                                                             v['value'])
                    v['complete'][self.dev] = True
            time.sleep(1)
        while True:
            self.send_command('set_voltage', 24)
            self.send_command('set_current', .5)
            self.send_command('set_output', 0)
            self.send_command('set_auto_output', 0)
            self.send_command('read_set_voltage')
            self.send_command('read_set_current')
            self.send_command('read_output_state')
            while True:
                self.send_command('read_actual_voltage')
                self.send_command('read_actual_current')
                self.send_command('read_actual_output_capacity')
                time.sleep(1)

    def send_command(self, command_name, value=None):
        command = config['command'][command_name]
        formatedvalue = ''
        if command['format'] is not False:
            if command['scale'] is not 1:
                value = int(round(value * command['scale']))
            if value < command['min']:
                value = command['min']
            if value > command['max']:
                value = command['max']
            formatedvalue = command['format'].format(value)
        reply = self.uart_IO(self.address + command['cmd']
                             + formatedvalue + '\r\n')
        regex = "^#" + command['cmd'] + command['regex']
        if re.match(regex, reply):
            value = re.findall(command['regex'], reply)
            if command['regex'] != value[0]:
                value = int(value[0])
                if command['scale'] is not 1:
                    value = float(value) / command['scale']
            else:
                value = str(value[0])
            print self.dev + ' value = ' + str(value)
            return(value)
        else:
            raise Exception('error uart returned bad string = ' + str(reply))

    def uart_IO(self, output):
        timeout = 0
        while (self.ser.out_waiting > 0 and self.ser.in_waiting > 0
               and self.busy):
            timeout += 1
            if timeout > 20 and not self.busy:
                self.ser.reset_output_buffer()
                self.ser.reset_input_buffer()
                timeout = 0
                raise Exception('serial write timeout ' + str(self.dev))
            time.sleep(0.01)
        self.busy = True
        self.ser.write(output.encode())
        print self.dev + ' sent = ' + str(re.sub('\n|\r', '', output))
        endofline = False
        timeout = 0
        reply = ''
        while not endofline:
            if self.ser.in_waiting > 0:
                reply_stream = self.ser.read()
                reply += re.sub('\n|\r', '', reply_stream)
                if re.match('\n', reply_stream):
                    endofline = True
            else:
                timeout += 1
                if timeout > 20:
                    endofline = True
                    raise Exception('serial read timeout ' + str(self.dev))
                time.sleep(0.01)
        self.busy = False
        return(reply)


threadLock = threading.Lock()
handle_control_t = handle_control('control')
handle_control_t.daemon = True
handle_control_t.start()

while True:
    time.sleep(1)
