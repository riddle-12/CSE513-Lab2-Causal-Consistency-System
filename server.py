import socket
import sys
import os
import types
import time
import selectors
import threading
import pickle
import time
sel = selectors.DefaultSelector()

HOST = '127.0.0.1'  # server's host address
PORT1 = 42000 # server's port number
PORT2 = 42010 
PORT3 = 42020 
size = 128
PORT = [62000, 62010, 62020]

lamport_time=0

'''
Datacenter:
1. store data (key : value)
2. for each client, maintain a dependency list (key, (timestamp, datacenter_id))
3. knows clients' and other datacenters' portnumbers
'''

'''current datacenterID, portnumber, data value and clients' lists stored in datacenter'''
class datacenter:
    def __init__(self, id, datacenter_port, key_value_version):
        self.id = id   # current datacenter ID
        self.datacenter_port = datacenter_port #current datacenter port number
        self.key_value_version = key_value_version # dict(list)--(key1:(value1,version1), key2:(value2,version2)
        # self.client_lists = client_lists # (???)

class LamportClock:
    def __init__(self):
        self.time = 0 

    def receive_message(message):
        global lamport_time
        recv_time = message['time']
        if recv_time > lamport_time:
            lamport_time = recv_time
        print('Recieve Lamport Clock of', recv_time)
        return message

    def send_message(message):
        global lamport_time
        print('Current time:', lamport_time)
        lamport_time += 1
        print('Time is now:', lamport_time)
        message['time'] = lamport_time
        return message


def Requesthandler(cur_datacenter, conn, addr, client_list):
    print('Enter the handler')
    while True:
        #print('111')
        try:
            data1 = conn.recv(2048)
            request_argu = pickle.loads(data1)
            print(request_argu)

            if request_argu[0] == 'read': # 'read' read_key
                print('Received a read request from client on key =', request_argu[1])
                read_key = request_argu[1]
                if cur_datacenter.key_value_version.get(read_key) == None: 
                    conn.sendall(pickle.dumps('There is no such key in this datacenter!'))
                else:
                    LamportClock.receive_message(request_argu[2])
                    key_value = cur_datacenter.key_value_version.get(read_key)[0] 
                    key_version = cur_datacenter.key_value_version.get(read_key)[1] 
                    print('requested_key_value_version:', read_key, key_value, key_version)  
                    conn.sendall(pickle.dumps( [read_key, key_value,lamport_time]))
                    
                    client_list.append([read_key, key_version]) 
                    print('Appended', (read_key, key_version), 'to this client_list!')

            if request_argu[0] == 'write': # 'write' write_key write_value lamport_time
                write_key = request_argu[1]
                write_value = request_argu[2]
                LamportClock.receive_message(request_argu[3])
                print('Received a write request from client on key =', write_key, 'change value to', write_value, 'Lamport Clock Value is', lamport_time)
                # update the stored key value
                version = [lamport_time, cur_datacenter.id]
                print('cur_datacenter,id=', cur_datacenter.id)
                cur_datacenter.key_value_version[write_key] = (write_value, version)
                print('cur_datacenter.key_value_version = ', cur_datacenter.key_value_version)
                # propogate the replicated write request to other datacenter
                for i in range(len(PORT)):
                    if i != cur_datacenter.id:
                        delay = 0
                        if abs(cur_datacenter.id - i) == 2:
                            delay = 15
                        else:
                            delay = abs(cur_datacenter.id - i)
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as ss:
                            ss.connect((HOST, PORT[i]))
                            print('Successfully connected to another datacenter', i, '!')
                            time.sleep(delay) 
                            ss.sendall(pickle.dumps(('replicated write request', write_key, write_value, client_list,lamport_time,cur_datacenter.id)))
                            print('Sent out the replicated write request!')
                # update current client_list
                client_list = []
                client_list.append([write_key, version])

            if request_argu[0] == 'replicated write request':
                write_key = request_argu[1]
                write_value = request_argu[2]
                client_list = request_argu[3]
                write_time = request_argu[4]
                write_dcId = request_argu[5]
                print('Received a replicated request from dataserver', write_dcId, ':', request_argu[1:3])
                # dependency check   # if satisfy, commit the write request  # if not, delay until get satisfied
                while dependency_check(cur_datacenter, client_list) == 0:
                    print('Dependency condition is not satisfied, wait--')
                    time.sleep(1)
                if dependency_check(cur_datacenter, client_list) == 1:
                    print('Dependency condition is satisfied, commit the request!')
                    cur_datacenter.key_value_version[write_key] = [write_value, [write_time, write_dcId]]
                    print('Local data and version are updated to', cur_datacenter.key_value_version)
              
                  
 
        except EOFError:
            print("Client", addr ,"Seems Offline, stop serving it!")
            conn.close()
            return 

def dependency_check(cur_datacenter, client_list):
    print('Processing dependency check now.')
    print('Recieved client_list is', client_list)
    # check if already received the same version in client_list
    if client_list:
        key = client_list[0][0]
        print('key =', key)
        value_version = cur_datacenter.key_value_version.get(key)   # value, [version]
        print('value_version =', value_version)
        if value_version[1] == client_list[0][1]:
            return 1
        else:
            return 0
    else:
        return 1




'''Main routine and Set up the listening socket'''
if __name__ == "__main__":

    '''Initialize the datacenter'''
    cur_ID = int(input('Please enter current datacenter ID to initialize:'))
    cur_datacenter_port = PORT[cur_ID]
    tmp = {'x': [0, [0, cur_ID]], 'y': [0, [0, cur_ID]], 'z': [0, [0, cur_ID]]}
    cur_datacenter = datacenter(cur_ID, cur_datacenter_port, tmp)
    print('cur_datacenter.key_value_version = ', cur_datacenter.key_value_version)

    '''create a server socket to listen on'''
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, cur_datacenter_port))
        s.listen()
        ##Used to make a seperate thread for every request
        #def making_thread(s):
        while True:
            conn, addr = s.accept()
            print('Accepted connection from', addr)

            # create a new dependency list for the connected client
            client_list = list()

            threading.Thread(target = Requesthandler, args = (cur_datacenter, conn, addr, client_list)).start()

            
        
            '''
            cur_thread = threading.Thread(target = register_reply, args = (conn, IP_port_filename))
            cur_thread.start()
            '''

              
