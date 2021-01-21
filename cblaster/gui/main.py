"""A basic GUI for cblaster."""

import os
from threading import Thread, Event
import subprocess
from queue import Queue, Empty

import PySimpleGUI as sg

from cblaster import __version__
from cblaster import main, extract as cb_extract
from cblaster.gui import search, makedb, citation, gne, extract, extract_clusters


sg.theme("Lightgrey1")


def Column(layout, scrollable=False):
    return sg.Column(
        layout,
        scrollable=scrollable,
        size=(540, 480),
        vertical_scroll_only=True
    )


def run_cblaster(values, textbox):
    """Handles conversion of PySimpleGUI values to cblaster parameters.

    - Know which workflow tab we're on (search or makedb)
    - search
        - Know which search mode tab we're on
        - if remote, use entrez query, database, RID
        - if local, jdb and database

    Args:
        values (dict): Dictionary of values from PySimpleGUI.
    """
    if values["cblaster_tabs"] == "Search":
        args = dict(
            query_file=values["query_file"],
            query_ids=values["query_ids"],
            session_file=values["session_file"],
            mode=values["search_mode"],
            gap=values["gap"],
            unique=values["unique"],
            min_hits=values["min_hits"],
            require=values["require"],
            min_identity=values["min_identity"],
            min_coverage=values["min_coverage"],
            max_evalue=values["max_evalue"],
            recompute=values["recompute"],
        )

        if values["search_mode"] == "remote":
            args.update(
                database=values["database"],
                entrez_query=values["entrez_query"],
                rid=values["rid"]
            )
        else:
            args.update(
                database=values["dmnd_database"],
                cpus=values["cpus"]
            )

        if values["summary_gen"]:

            if values["summary_text"]:
                args["output"] = values["summary_text"]

            args.update(
                output_decimals=values["summary_decimals"],
                output_delimiter=values["summary_delimiter"],
                output_hide_headers=values["summary_hide_headers"]
            )

        if values["binary_gen"]:
            args.update(
                binary=values["binary_text"],
                binary_delimiter=values["binary_delimiter"],
                binary_hide_headers=values["binary_hide_headers"],
                binary_decimals=values["binary_decimals"],
                binary_attr=values["binary_attr"],
                binary_key=values["binary_key"],
            )

        if values["figure_gen"]:
            plot = values["figure_text"] if values["figure_text"] else True
            args.update(plot=plot)

        # Overwrite any placeholder text
        for arg, value in args.items():
            if isinstance(value, str) and value.startswith("e.g."):
                args[arg] = ""
        subcommand = values["cblaster_tabs"]

    elif values["cblaster_tabs"] == "Makedb":
        # TODO add all possible values
        args = dict(
            blank1=" ".join(values["makedb_genbanks"].split(";")),
            name=values["makedb_filename"],
            indent=values["json_indent"]
        )
        subcommand = values["cblaster_tabs"]

    elif values["cblaster_tabs"] == "Neighbourhood":
        # TODO add all possible values
        args = dict(
            blank1=values["session"],
            max_gap=int(values["max_gap"]),
            samples=int(values["samples"]),
            scale=values["scale"],
            output=values["output"],
        )
        subcommand = "gne"

    elif values["cblaster_tabs"] == "Extract":
        args = dict(
            blank1=values["extract_session"],
            delimiter=values["delimiter"],
            name_only=values["name_only"],
            download=values["download"],
            output=values["extract_output"],
            queries=values["queries"],
            organisms=values["organisms"],
            scaffolds=values["scaffolds"],
        )
        subcommand = values["cblaster_tabs"]
    elif values["cblaster_tabs"] == "Extract Clusters":
        args = dict(
            blank1=values["extract_clusters_session"],
            output=values["extract_clusters_output"],
            prefix=values["prefix"],
            format=values["output format"],
            maximum_clusters=values["max clusters"],
            clusters=values["clusters"],
            score_threshold=values["score threshold"],
            organisms=values["organisms ec"],
            scaffolds=values["scaffolds ec"],
        )
        subcommand = "extract_clusters"
    else:
        raise ValueError("Expected 'Search', 'Makedb', 'Neighbourhood' or 'Extract'")

    return create_cblaster_command(subcommand, args, textbox)


main_gui_layout = [
    [sg.Text("cblaster", font="Arial 18 bold", pad=(0, 0))],
    [sg.Text(f"v{__version__}", font="Arial 10", pad=(0, 0))],
    [sg.Text("Cameron Gilchrist, 2020", font="Arial 10", pad=(0, 0))],
    [sg.TabGroup([
        [sg.Tab("Search", [[Column(search.layout, scrollable=True)]])],
        [sg.Tab("Neighbourhood", [[Column(gne.layout)]])],
        [sg.Tab("Makedb", [[Column(makedb.layout)]])],
        [sg.Tab("Extract", [[Column(extract.layout, scrollable=True)]])],
        [sg.Tab("Extract Clusters", [[Column(extract_clusters.layout, scrollable=True)]])],
        [sg.Tab("Citation", [[Column(citation.layout)]])],
    ], enable_events=True, key="cblaster_tabs"
    )],
    [sg.Button("Start", key="start_button", button_color=["white", "green"]),
     sg.Button("Exit", key="exit_button", button_color=["white", "red"])],
]


def cblaster_gui():

    main_window = sg.Window(
        "cblaster",
        main_gui_layout,
        size=(600, 660),
        element_padding=(5, 5),
        element_justification="center",
        finalize=True
    )
    command_thread = None
    command_window = None
    while True:
        event, values = main_window.read()

        if event in (None, "exit_button"):
            break

        # Disable binary & summary table, figure options if not enabled
        for key in ("browse", "text", "delimiter", "decimals", "hide_headers", "key", "attr"):
            main_window[f"binary_{key}"].update(disabled=not values["binary_gen"])

        for key in ("browse", "text", "decimals", "hide_headers", "delimiter"):
            main_window[f"summary_{key}"].update(disabled=not values["summary_gen"])

        for key in ("browse", "text"):
            main_window[f"figure_{key}"].update(disabled=not values["figure_gen"])

        # Disable start button when on citation tab
        main_window["start_button"].update(
            disabled=values["cblaster_tabs"]
            not in ("Search", "Makedb", "Neighbourhood", "Extract", "Extract Clusters")
        )

        if event == "start_button":
            main_window["start_button"].update(disabled=True)
            command_window = create_command_window()
            command_thread = run_cblaster(values, command_window["textbox"])
            command_thread.start()
        if command_window is not None:
            event2, values2 = command_window.read()
            if event2 in (None, "exit_button"):
                if not command_thread.is_finished():
                    command_thread.stop()
                    command_thread.join()
                command_window.close()
                command_window = None
                main_window["start_button"].update(disabled=False)

    main_window.close()


def create_command_window():
    command_gui_layout = [
        [sg.Text("cblaster", font="Arial 18 bold", pad=(0, 0))],
        [sg.Text(f"v{__version__}", font="Arial 10", pad=(0, 0))],
        [sg.Text("Cameron Gilchrist, 2020", font="Arial 10", pad=(0, 0))],
        [sg.Multiline(key="textbox", size=(500, 20), disabled=True)],
        [sg.Button("Exit", key="exit_button", button_color=["white", "red"])],
    ]
    command_window = sg.Window(
        "cblaster command",
        command_gui_layout,
        size=(500, 560),
        element_padding=(5, 5),
        element_justification="center",
        finalize=True
    )
    return command_window


class CommandThread(Thread):

    def __init__(self, command, textbox):
        super().__init__(daemon=True)
        self.command = command
        self.textbox = textbox
        self.stderr_queue = Queue()
        self.__finished = Event()

    def enqueue_output(self, out, queue):
        for line in iter(out.readline, b''):
            queue.put(line)

    def run(self):
        popen = subprocess.Popen(self.command, shell=False, stderr=subprocess.PIPE)

        # this thread is neccesairy to be able to read stderr while also being able to terminate the subprocess
        t = Thread(target=self.enqueue_output, args=(popen.stderr, self.stderr_queue))
        t.daemon = True  # thread dies with the program
        t.start()
        while popen.poll() is None:
            if self.__finished.is_set():
                # make sure to terminate before any of these possible calls is made to prevent error
                popen.kill()
                popen.wait()
                return
            try:
                line = self.stderr_queue.get_nowait()  # or q.get(timeout=.1)
            except Empty:
                continue
            else:  # got line
                # prevent double newlines
                str_line = line.decode("utf-8").replace(os.linesep, "")
                self.textbox.update(self.textbox.get() + str_line)

        # make sure to call communicate to properly finish process
        output, error = popen.communicate()
        self.__finished.set()

    def stop(self):
        self.__finished.set()

    def is_finished(self):
        return self.__finished.is_set()


def create_cblaster_command(subcommand, arguments, textbox):
    command = f"cblaster {subcommand.lower()}"
    for key, value in arguments.items():
        if value in ["", False]:
            continue
        elif value is True:
            command += f" --{key}"
        elif "blank" in key:
            command += f" {value}"
        else:
            command += f" --{key} {value}"
    return CommandThread(command, textbox)


if __name__ == "__main__":
    cblaster_gui()
