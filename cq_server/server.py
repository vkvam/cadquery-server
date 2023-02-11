'''Module server: used to run the Flask web server.'''

import json
import queue
import time
import uuid
from threading import Thread
from queue import Queue
from time import sleep
import os.path as op
from typing import Tuple

from flask import Flask, request, render_template, make_response, Response

from .module_manager import ModuleManager

WATCH_PERIOD = 0.3
SSE_MESSAGE_TEMPLATE = 'event: file_update\ndata: {data}\nid: {id}\n\n'

app = Flask(__name__, static_url_path='/static')


def run(port: int, module_manager: ModuleManager, ui_options: dict, is_dead: bool = False) -> None:
    '''Run the Flask web server.'''

    @app.route('/', methods=['GET'])
    def _root() -> str:
        if module_manager.target_is_dir:
            module_manager.module_name = request.args.get('m')

        return render_template(
            'viewer.html',
            options=ui_options,
            modules_name=list(module_manager.available_modules.keys()),
            data=module_manager.get_data()
        )

    @app.route('/html', methods=['GET'])
    def _html() -> str:
        # pylint: disable=import-outside-toplevel

        from .exporter import Exporter

        if module_manager.target_is_dir:
            module_manager.module_name = request.args.get('m')

        exporter = Exporter(module_manager)
        return exporter.get_html(ui_options)

    @app.route('/json', methods=['GET'])
    def _json() -> Tuple[str, int]:
        if module_manager.target_is_dir:
            module_manager.module_name = request.args.get('m')

        data = module_manager.get_data()
        return data, (400 if 'error' in data else 200)

    @app.route('/events', methods=['GET'])
    def _events() -> Response:

        def stream():
            c = 0
            while True:
                try:
                    data = events_queue.get(block=True, timeout=1)
                    print(f'Sending Server Sent Event: {len(data)}...')
                    yield data
                except queue.Empty:
                    yield f"event: keep_alive\ndata: {c}\nid: {str(uuid.uuid4())}\n\n"
                    if c % 100 == 0:
                        print(f"{c}")
                    c += 1

        response = make_response(stream())
        response.mimetype = 'text/event-stream'
        response.headers['Cache-Control'] = 'no-store, must-revalidate'
        response.headers['Expires'] = 0
        return response

    def watchdog() -> None:
        while True:
            last_updated_file = module_manager.get_last_updated_file()

            if last_updated_file:
                module_manager.module_name = op.basename(last_updated_file)[:-3]
                data = module_manager.get_data()
                events_queue.put(SSE_MESSAGE_TEMPLATE.format(data=json.dumps(data), id=str(uuid.uuid4())))
            sleep(WATCH_PERIOD)

    events_queue = Queue(maxsize=30)
    module_manager.init()

    if not is_dead:
        watchdog_thread = Thread(target=watchdog, daemon=True)
        watchdog_thread.start()

    app.run(host='0.0.0.0', port=port, debug=False)
