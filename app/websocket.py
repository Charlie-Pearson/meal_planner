from flask import request
from flask_login import current_user
from flask_socketio import join_room, leave_room
from flask import current_app

from . import socketio


def register_handlers(sio):
    @sio.on('connect')
    def handle_connect():
        current_app.logger.debug(f'[WEBSOCKET] Client connected: {request.sid}')

    @sio.on('disconnect')
    def handle_disconnect():
        current_app.logger.debug(f'[WEBSOCKET] Client disconnected: {request.sid}')

    @sio.on('join_shopping_list')
    def on_join_shopping_list():
        account = current_user.accounts.first()
        if account:
            room = f'shopping_list_{account.id}'
            join_room(room)
            current_app.logger.debug(f'[WEBSOCKET] Client {request.sid} joined room {room}')

    @sio.on('leave_shopping_list')
    def on_leave_shopping_list():
        account = current_user.accounts.first()
        if account:
            room = f'shopping_list_{account.id}'
            leave_room(room)
            current_app.logger.debug(f'[WEBSOCKET] Client {request.sid} left room {room}')
