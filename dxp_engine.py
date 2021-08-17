import dxp.dxp_run as dxp
import draughts
import subprocess
import os
import signal
import threading
import time
import logging

logger = logging.getLogger(__name__)


class Engine:
    def __init__(self, command, options, ENGINE=5):
        self.command = command
        self.ENGINE = ENGINE
        self.info = {}
        self.id = {}
        self.console = dxp.tConsoleHandler
        self.receiver = dxp.tReceiveHandler
        self.game_started = False
        self.old_moves = []
        self.last_move = None

        self.initial_time = options.pop("initial-time")

        self.engine_opened = False  # Whether the engine is already open or lidraughts-bot should open it
        self.ip = '127.0.0.1'
        self.port = '27531'
        self.wait_to_open_time = 10

        for name, value in options.items():
            self.setoption(name, value)

        if not self.engine_opened:
            cwd = os.path.realpath(os.path.expanduser("."))
            command = list(filter(bool, self.command))
            command = subprocess.list2cmdline(command)
            self.p = self.open_process(command, cwd)

        self.start_time = time.perf_counter_ns()

    def setoption(self, name, value):
        if name == 'engine_opened':
            self.engine_opened = value
        elif name == 'ip':
            self.ip = str(value)
        elif name == 'port':
            self.port = str(value)
        elif name == 'wait_time':
            self.wait_to_open_time = int(value)

    def open_process(self, command, cwd=None, shell=True, _popen_lock=threading.Lock()):
        kwargs = {
            "shell": shell,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.PIPE,
            "bufsize": 1,  # Line buffered
            "universal_newlines": True,
        }
        logger.debug(f'command: {command}, cwd: {cwd}')

        if cwd is not None:
            kwargs["cwd"] = cwd

        # Prevent signal propagation from parent process
        try:
            # Windows
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        except AttributeError:
            # Unix
            kwargs["preexec_fn"] = os.setpgrp

        with _popen_lock:  # Work around Python 2 Popen race condition
            return subprocess.Popen(command, **kwargs)

    def kill_process(self):
        if not self.engine_opened:
            try:
                # Windows
                self.p.send_signal(signal.CTRL_BREAK_EVENT)
            except AttributeError:
                # Unix
                os.killpg(self.p.pid, signal.SIGKILL)

            self.p.communicate()

    def connect(self):
        if not self.engine_opened:
            wait_time = self.start_time / 1e9 + self.wait_to_open_time - time.perf_counter_ns() / 1e9
            logger.debug(f'wait time: {wait_time}')
            if wait_time > 0:
                time.sleep(wait_time)
        self.console.run_command(f'connect {self.ip} {self.port}')

    def start(self, board, time):
        self.connect()
        color = 'B' if board.whose_turn() == draughts.WHITE else 'W'
        time = str(round(time // 60))
        moves = '300'
        self.console.run_command(f'setup {board.initial_fen} {board.variant}')
        self.console.run_command(f'gamereq {color} {time} {moves}')
        accepted = self.recv_accept()
        logger.debug(f'Aceepted: {accepted}')
        self.id["name"] = dxp.current.engineName

    def recv_accept(self):
        while True:
            if dxp.accepted is not None:
                return dxp.accepted

    def recv_move(self):
        while True:
            if self.last_move != dxp.last_move:
                self.last_move = dxp.last_move
                logger.debug(f'new last move: {self.last_move}')
                return self.last_move

    def play(self, board, ponder):
        if not self.game_started:
            self.start(board, self.initial_time)
            self.game_started = True
        if board.move_stack:
            move = board.move_stack[-1]
            move = [move[i:i+2] for i in range(0, len(move), 2)]
            move = '-'.join(move)
            self.console.run_command(f'sm {move}')
        best_move = self.recv_move()
        return best_move

    def quit(self):
        self.console.run_command('gameend 0')
