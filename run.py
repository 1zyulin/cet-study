import argparse
import threading
import webbrowser

from waitress import serve

from app import create_app


def main():
    parser = argparse.ArgumentParser(description='CET Study 本地学习平台')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('端口须在 1024—65535 之间')
    app = create_app()
    url = f'http://127.0.0.1:{args.port}'
    print(f'CET Study v0.1.0\nLocal URL: {url}\n关闭本窗口或按 Ctrl+C 停止。', flush=True)
    if not args.no_browser:
        threading.Timer(1, lambda: webbrowser.open(url)).start()
    serve(app, host='127.0.0.1', port=args.port, threads=8)


if __name__ == '__main__':
    main()
