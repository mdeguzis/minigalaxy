import shutil
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GdkPixbuf
import requests
import os
import threading
import subprocess
from minigalaxy.directories import CACHE_DIR, THUMBNAIL_DIR, UI_DIR


@Gtk.Template.from_file(os.path.join(UI_DIR, "gametile.ui"))
class GameTile(Gtk.Box):
    __gtype_name__ = "GameTile"

    image = Gtk.Template.Child()
    button = Gtk.Template.Child()

    def __init__(self, game=None, api=None):
        Gtk.Frame.__init__(self)
        self.game = game
        self.api = api
        self.progress_bar = None
        self.installed = False

        self.image.set_tooltip_text(self.game.name)

        self.install_dir = self.api.config.get("install_dir")
        self.game_install_dir = os.path.join(self.install_dir, self.game.name)
        self.download_dir = os.path.join(CACHE_DIR, "download")
        self.executable_path = os.path.join(self.game_install_dir, "start.sh")
        self.download_path = os.path.join(self.download_dir, "{}.sh".format(self.game.name))
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)

        self.__load_state()

        image_thread = threading.Thread(target=self.__load_image)
        image_thread.daemon = True
        image_thread.start()

    def __str__(self):
        return self.game.name

    @Gtk.Template.Callback("on_button_clicked")
    def on_button_click(self, widget) -> None:
        if self.installed:
            return
        self.__create_progress_bar()
        widget.set_sensitive(False)
        widget.set_label("downloading...")
        download_thread = threading.Thread(target=self.__download_file)
        download_thread.start()

    def __load_image(self) -> None:
        # image_url = "https:" + self.image_url + "_392.jpg" #This is the bigger image size
        image_url = "https:{}_196.jpg".format(self.game.image_url)
        filename = os.path.join(THUMBNAIL_DIR, "{}.jpg".format(self.game.id))
        if not os.path.isfile(filename):
            if not os.path.exists(THUMBNAIL_DIR):
                os.makedirs(THUMBNAIL_DIR)
            download = requests.get(image_url)
            with open(filename, "wb") as writer:
                writer.write(download.content)
                writer.close()
        self.image.set_from_file(filename)

    def __download_file(self) -> None:
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)
        download_info = self.api.get_download_info(self.game)
        file_url = download_info["downlink"]
        data = requests.get(file_url, stream=True)
        handler = open(self.download_path, "wb")

        total_size = int(data.headers.get('content-length'))
        downloaded_size = 0
        chunk_count = 0
        for chunk in data.iter_content(chunk_size=4096):
            if chunk:
                chunk_count += 1
                handler.write(chunk)
                downloaded_size += len(chunk)
                # Only update the progress bar every 2 megabytes
                if chunk_count == 4000:
                    percentage = downloaded_size / total_size
                    self.progress_bar.set_fraction(percentage)
                    self.progress_bar.show_all()
                    chunk_count = 0
        handler.close()
        self.progress_bar.destroy()
        self.__install_game()
        self.__load_state()

    def __install_game(self) -> None:
        # Make a temporary directory for extracting the installer
        temp_dir = os.path.join(CACHE_DIR, "extract/{}".format(self.game.id))
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

        os.makedirs(temp_dir)

        # Extract the game files
        subprocess.call(["unzip", "-qq", self.download_path, "-d",
                         temp_dir])

        # Make sure the install directory exists
        if not os.path.exists(self.install_dir):
            os.makedirs(self.install_dir)

        # Copy the game files into the correct directory
        os.rename(os.path.join(temp_dir, "data/noarch"), self.game_install_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)
        os.remove(self.download_path)

    def __create_progress_bar(self) -> None:
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_halign(Gtk.Align.CENTER)
        self.progress_bar.set_size_request(196, -1)
        self.progress_bar.set_hexpand(False)
        self.progress_bar.set_vexpand(False)
        self.set_center_widget(self.progress_bar)
        self.progress_bar.set_fraction(0.0)
        self.show()

    def __load_state(self) -> None:
        if os.path.isfile(self.executable_path):
            self.installed = True
            self.button.set_label("play")
            self.button.set_sensitive(True)
            self.button.connect("clicked", self.__start_game)
        else:
            self.installed = False
            self.button.set_label("download")

        self.button.show()

    def __start_game(self, widget) -> subprocess:
        game = subprocess.Popen([self.executable_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            game.wait(timeout=float(5))
        except subprocess.TimeoutExpired:
            return game

        # Now deal with the error we've received
        stdout, stderror = game.communicate()
        error_text = "Failed to start {}:".format(self.game.name)
        error_message = stderror.decode("utf-8")
        print(error_text)
        print(error_message)
        dialog = Gtk.MessageDialog(
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text=error_text
        )
        dialog.format_secondary_text(error_message)
        dialog.run()
        dialog.destroy()

    def __lt__(self, other):
        names = [str(self), str(other)]
        names.sort()
        if names[0] == str(self):
            return True
        return False
