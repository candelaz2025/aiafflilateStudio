"""One-click local Windows launcher. Chooses a free port, no cloud server required."""
from __future__ import annotations
import socket
import sys
import threading
import webbrowser

import uvicorn


def free_port():
    for port in (8000,8010,8011,8012,8020):
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
            try:sock.bind(('127.0.0.1',port))
            except OSError:continue
            return port
    raise RuntimeError('พอร์ต 8000/8010/8011/8012/8020 มีโปรแกรมอื่นใช้งาน กรุณาปิดโปรแกรมอื่นก่อน')


def main():
    port=free_port()
    url=f'http://127.0.0.1:{port}'
    print('Affiliate Auto Studio PC V6 — กำลังเปิดหน้าแดชบอร์ด',flush=True)
    print('Open:',url,flush=True)
    timer=threading.Timer(1.8,lambda:webbrowser.open(url))
    timer.daemon=True
    timer.start()
    uvicorn.run('app:app',host='127.0.0.1',port=port,workers=1,log_level='info')

if __name__=='__main__':main()
