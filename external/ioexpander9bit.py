# IO Expander 9-bit module v1.1
import serial
import datetime
import time
import termios

SERIAL_TIMEOUT = 5.0

ser = serial.Serial(
    port='/dev/serial0',
    baudrate=115200,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS,
    timeout=5
)

import select, socket
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.setblocking(False)
host = '' # 192.168.0.10 or localhost
port = 1234
server.bind((host, port))
server.listen(5)
inputs = [server]
outputs = []

# extra termios flags
CMSPAR = 0x40000000  # Use "stick" (mark/space) parity

# select SPACE parity to clear the address bit
def SerialSPACEParity():
    iflag,oflag,cflag,lflag,ispeed,ospeed,cc = termios.tcgetattr(ser)
    cflag |= termios.PARENB | CMSPAR
    cflag &= ~termios.PARODD
    termios.tcsetattr(ser, termios.TCSANOW, [iflag,oflag,cflag,lflag,ispeed,ospeed,cc])

# select MARK parity to set the address bit
def SerialMARKParity():
    iflag,oflag,cflag,lflag,ispeed,ospeed,cc = termios.tcgetattr(ser)
    cflag |= termios.PARENB | CMSPAR | termios.PARODD
    termios.tcsetattr(ser, termios.TCSANOW, [iflag,oflag,cflag,lflag,ispeed,ospeed,cc])    

# select the IO Expander board by setting the 9th or address bit
def SerialWriteBoard(board):
    if board is not None and board > 0:
        SerialMARKParity()        
        ser.write(bytes(chr(board),'raw_unicode_escape'))
        SerialSPACEParity()

def SerialAddress(board):
    SerialWriteBoard(board)
    TelnetControl(bytes(str(board),'raw_unicode_escape') + b':')
    

# read from the serial port 'until' char is read or 'length' characters received
def SerialReadUntil(board, cmd, until):
    bytes = b''
    sec = time.perf_counter()
    
    if (board is not None and board > 0):
        SerialAddress(board)
    if cmd is not None:
        ser.write(cmd + b'\r\n')
    while 1:
        if ser.in_waiting:
            ch = ser.read()
            TelnetControl(ch)
#            if ch == b'':
#                if len(bytes) == 0:
#                    return None
#                break
            if ch == until:
                break
            if ch != b'\r':
                bytes += ch
            sec = time.perf_counter()
        if time.perf_counter() - sec > SERIAL_TIMEOUT:
            TelnetControl(b'TIMEOUT\r\n')
            break
        
    return bytes
     
# bytes to hex bytes     
def btoh2(bytes):
    return bytes.fromhex(bytes.decode("ascii"))

# bytes to long
def btol2(bytes):
    return int(bytes)

# bytes to decimal. ending returned
def btoi2(bytes, start):
    end = start
    while end < len(bytes) and bytes[end] >= ord('0') and bytes[end] <= ord('9'):        
        end += 1
    if (start == end):
        return 0, end
    return int(bytes[start:end]), end+1

# read serial bytes
def SerialReadBytes():
    return SerialReadUntil(None, None, b'\n')

# read serial int
def SerialReadInt():
    buffer = SerialReadBytes()
    if buffer is not None:
        return btol2(buffer)
    
    return None

def SerialReadHex():
    buffer = SerialReadBytes()
    if buffer is not None:
        return btoh2(buffer)
    
    return None

def SerialReadFloat():
    buffer = SerialReadBytes()
    if buffer is not None:
        if buffer[0] > ord('9'):
            return None
        value = float(buffer.decode('raw_unicode_escape'))
        return value
        
    return None        

# send serial cmd wait for CR returned
def SerialCmd(board, cmd):
    return SerialReadUntil(board, cmd, b'\n')

# send serial cmd, wait for '>' returned
def SerialCmdDone(board, cmd):
    return SerialReadUntil(board, cmd, b'>')

# wait for '>' returned
def SerialReadUntilDone():
    return SerialReadUntil(None, None, b'>')

# send serial cmd and check for error returned
def SerialCmdNoError(board, cmd):
    noerror = False
    
    if SerialCmd(board, cmd) is not None:
        response = SerialReadBytes()
        if response is not None:
            if response[0] == ord('n'):
                noerror = True

        SerialReadUntilDone()

    return noerror

# send binary serial bitmap using ascii mode
def SerialDisplayBitmap(board, x, y, w, h, bitmap):
    bw = (w+7)>>3
    size = 0
    ascii = False
    n = 0
    
    for i in range(h):
        if not size:
            SerialAddress(board)                
            ser.write(b'sb')
            ser.write(bytes(str(x),'raw_unicode_escape'))
            ser.write(b',')
            ser.write(bytes(str(y+i),'raw_unicode_escape'))
            ser.write(b',')
            ser.write(bytes(str(w),'raw_unicode_escape'))
            ser.write(b',')
            ascii = False
        for j in range(bw):
            ch = bitmap[n]
            n += 1
            if ch == ord(b'"') or ch == 8 or ch == 13:
                if ascii:
                    ser.write(b'"')
                #if ch < 0x10:
                #    ser.write(b'0')
                ser.write(bytes(hex(ch)[2:].zfill(2),'raw_unicode_escape'))
                if size+j < 99:
                    ser.write(b',')
                ascii = False
            else:
                if not ascii:
                    ser.write(b'"')
                    ascii = True
                ser.write(bytes(chr(ch),'raw_unicode_escape'))
        size += bw
        if i == h-1 or size > 100:
            SerialCmdDone(None, b'')
            size = 0
            
# serial read time
def SerialReadTime(board):
    clk = []
    
    if SerialCmd(board, b'sr') is not None:
        buffer = SerialReadBytes()
        if buffer is not None:
            start = 0
            for _ in range(6):
                value,start = btoi2(buffer, start)
                clk.append(value)
        SerialReadUntilDone()
        dt = datetime.datetime(clk[2]+2000,clk[0],clk[1],clk[3],clk[4],clk[5],0)
        tm = time.localtime(dt.timestamp())
        return tm
        
    return None

# serial write time
def SerialWriteTime(board, clk):
    SerialAddress(board)
    ser.write(b'sc')
    ser.write(bytes(str(clk.tm_mon),'raw_unicode_escape'))
    ser.write(b'/')
    ser.write(bytes(str(clk.tm_mday),'raw_unicode_escape'))
    ser.write(b'/')
    ser.write(bytes(str(clk.tm_year-2000),'raw_unicode_escape'))
    ser.write(b' ')
    ser.write(bytes(str(clk.tm_hour),'raw_unicode_escape'))
    ser.write(b':')
    ser.write(bytes(str(clk.tm_min),'raw_unicode_escape'))
    ser.write(b':')
    ser.write(bytes(str(clk.tm_sec),'raw_unicode_escape'))
    return SerialCmdDone(None, b'')

# serial read EEPROM
def SerialReadEEPROM(board, address, length):
    size = 16
    data = b''

    while length:
        if size > length:
            size = length
        SerialAddress(board)
        ser.write(b'sr')
        ser.write(bytes(hex(address)[2:].zfill(4),'raw_unicode_escape'))
        ser.write(bytes(hex(size)[2:].zfill(2),'raw_unicode_escape'))
        SerialCmd(None, b'')
        buffer = SerialReadBytes()
        SerialReadUntilDone()
        data += btoh2(buffer)
        address += size
        length -= size
        
    return data    

# serial write EEPROM using ascii mode
def SerialWriteEEPROM(board, data, address):
    size = 0
    ascii = False
    n = 0
    
    length = len(data)
    while length:
        if not size:
            SerialAddress(board)       
            ser.write(b'sw')
            ser.write(bytes(hex(address)[2:].zfill(4),'raw_unicode_escape'))
            ascii = False
        ch = data[n]
        n += 1
        if ch == ord(b'"') or ch == 8 or ch == 13:
            if ascii:
                ser.write(b'"')
            ser.write(bytes(hex(ch)[2:].zfill(2),'raw_unicode_escape'))
            if length > 1 and size < 99:
                ser.write(b',')
            ascii = False
        else:
            if not ascii:
                ser.write(b'"')
                ascii = True
            ser.write(bytes(chr(ch),'raw_unicode_escape'))
        address += 1
        length -= 1
        size += 1
        if not length or size > 100:
            SerialCmdDone(None, b'')
            size = 0
           
    return True
    
# serial read button
def SerialReadButton(board, cmd):
    n = 0
    
    SerialCmd(board, cmd)
    n = SerialReadInt()
    SerialReadUntilDone()
    
    return n

# serial write relay expander using ascii mode
def SerialWriteRelayExpander(board, data):
    ascii = False
    n = 0
    
    length = len(data)
    SerialAddress(board)
    ser.write(b'es')
    while length:
        ch = data[n]
        n += 1
        if ch == ord(b'"') or ch == 8 or ch == 13:
            if ascii:
                ser.write(b'"')
            ser.write(bytes(hex(ch)[2:].zfill(2),'raw_unicode_escape'))
            if length > 1:
                ser.write(b',')
            ascii = False
        else:
            if not ascii:
                ser.write(b'"')
                ascii = True
            ser.write(bytes(chr(ch),'raw_unicode_escape'))
        length -= 1

    return SerialCmdDone(None, b'')

ioexpander_mode = False
mode_sec = 0.0
echo_chars = 0
cmd_buffer = b''

def TelnetControl(send):
    global ioexpander_mode, mode_sec, echo_chars, cmd_buffer

    try:
        readable, writable, exceptional = select.select(inputs, outputs, inputs, 0)
        for s in readable:
            if s is server:
                client, address = s.accept()
                client.setblocking(0)
                inputs.append(client)
                outputs.append(client)
                print('Connection from', address)
                # Force character mode on Pi 4 Telnet
                # IAC DO LINEMODE IAC WILL ECHO
                client.send(b'\xff\xfd\x22\xff\xfb\x01')
            else:
                data = s.recv(1024)
                #print('Receive', data)
                if data:
                    if data[0:1] == b'\x1b': # ESC
                        if ioexpander_mode:
                            s.send(b'\r\nExiting IO Expander Mode\r\n')
                            ioexpander_mode = False
                        else:
                            s.send(b'\r\nEntering IO Expander Mode\r\n>')
                            mode_sec = time.perf_counter()
                            ioexpander_mode = True
                    else:
                        if ioexpander_mode:
                            # Backspace or Linux Delete
                            if data[0:1] == b'\x08' or data[0:1] == b'\x7f':
                                if len(cmd_buffer):
                                    cmd_buffer = cmd_buffer[0:len(cmd_buffer)-1]
                                    s.send(b'\x08 \x08')
                            elif data[0:1] == b'\r': # Return
                                board = 0
                                s.send(b'\r')
                                if len(cmd_buffer):
                                    board,start = btoi2(cmd_buffer, 0)
                                    if cmd_buffer[start-1:start] == b':' and board:
                                        cmd_buffer = cmd_buffer[start:] + b'\r'
                                        SerialWriteBoard(board)
                                        for ch in cmd_buffer:
                                            ser.write(bytes(chr(ch),'raw_unicode_escape'))
                                            wait_sec = time.perf_counter()
                                            while not ser.in_waiting:
                                                time.sleep(0.001)
                                                if time.perf_counter() - wait_sec > SERIAL_TIMEOUT:
                                                    s.send(b'\nWait for Response Timeout\r\n>')
                                                    cmd_buffer = b''
                                                    return ioexpander_mode
                                            echo = ser.read()
                                        # Response
                                        wait_sec = time.perf_counter()
                                        while 1:
                                            if ser.in_waiting:
                                                ch = ser.read()
                                                s.send(ch)
                                                if ch == b'>':
                                                    break
                                                sec = time.perf_counter()
                                            if time.perf_counter() - sec > SERIAL_TIMEOUT:
                                                s.send(b'\nWait for Done Timeout\r\n>')
                                                cmd_buffer = b''
                                                return ioexpander_mode
                                    else:
                                        s.send(b'\nNo Board Address\r\n>')
                                    cmd_buffer = b''
                                else:
                                    s.send(b'\n>')
                            else:
                                cmd_buffer += data
                                s.send(data)
                            mode_sec = time.perf_counter()
                        else:
                            if data[0:1].upper() == b'C':
                                s.send(b'\r\nbye bye\r\n')
                                if s in outputs:
                                    outputs.remove(s)
                                inputs.remove(s)
                                s.close()
                                        
                else:
                    if s in outputs:
                        outputs.remove(s)
                    inputs.remove(s)
                    s.close()

        for s in writable:
            if len(send):
                s.send(send)

        for s in exceptional:
            inputs.remove(s)
            if s in outputs:
                outputs.remove(s)
            s.close()

        if ioexpander_mode:
            if ser.in_waiting:
                ch = ser.read()
                if echo_chars:
                    for s in writable:
                        s.send(ch)
                else:
                    echo_chars -= 1
            if time.perf_counter() - mode_sec > 60.0:
                for s in writable:
                    s.send(b'\r\nTimeout IO Expander Mode\r\n')
                ioexpander_mode = False    

    except AssertionError as error:
        print(error)

    return ioexpander_mode
