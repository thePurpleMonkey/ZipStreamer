import threading, datetime, struct, sys, os
from binascii import crc32
from dataclasses import dataclass
from pathlib import Path

class BinaryBuffer:
	def __init__(self):
		self.buffer = bytearray()

	def read(self):
		result = bytes(self.buffer[:])
		del self.buffer[:len(result)]
		return result

	def write(self, data):
		self.buffer.extend(data)

	def __len__(self):
		return len(self.buffer)

def file_modification_time(time: datetime.time):
	result = 0x00
	result |= time.second // 2
	result |= (time.minute) << 5
	result |= (time.hour) << 11
	return result.to_bytes(2, 'little')
	
def file_modification_date(date: datetime.date):
	result = 0x00
	result |= date.day
	result |= (date.month) << 5
	result |= (date.year - 1980) << 9
	return result.to_bytes(2, 'little')

@dataclass
class FileData:
	flags: bytes = b"\x00\x00"
	compression: bytes = b"\x00\x00"
	crc32: bytes = b"\x00\x00\x00\x00"
	last_modified_time: bytes = b"\x00\x00\x00\x00"
	last_modified_date: bytes = b"\x00\x00\x00\x00"
	uncompressed_size: bytes = b"\x00\x00\x00\x00"
	uncompressed_size: bytes = b"\x00\x00\x00\x00"
	header_offset: bytes = b"\x00\x00\x00\x00"

	filename: str = ""

class ZipStreamer(threading.Thread):
	VERSION = struct.pack("<H", 0x14)

	def __init__(self, output, *args, **kwargs):
		threading.Thread.__init__(self, *args, **kwargs)

		self.stop = False
		self.output = output
		self.input = BinaryBuffer()
		self.files = []
		self.offset = 0
		self.eof = False
		
	def run(self):
		while not self.eof:
			data = self.input.read()
			# if data:
			# print(f"Writing {len(data)} bytes...")
			self.output.write(data)
				
		# print(self.eof, self.input.buffer)
		self.output.write(self.input.read())
		self.output.close()

	def add_file(self, file, filename: str):
		data: str = file.read()
		crc32(b"\xde\xbb\x20\xe3")

		fd = FileData()
		fd.flags = b"\x00\x00"
		fd.compression = b"\x00\x00"
		fd.crc32 = struct.pack("<I", crc32(data))
		fd.filename = filename
		fd.header_offset = struct.pack("<I", self.offset)


		fd.last_modified_time = file_modification_time(datetime.datetime.now().time())
		fd.last_modified_date = file_modification_date(datetime.date.today())
		fd.uncompressed_size = struct.pack("<I", len(data))
		fd.compressed_size = fd.uncompressed_size

		self.files.append(fd)

		self._write(b"\x50\x4b\x03\x04")
		self._write(self.VERSION)
		self._write(fd.flags)
		self._write(fd.compression)
		self._write(fd.last_modified_time)
		self._write(fd.last_modified_date)
		self._write(fd.crc32)
		self._write(fd.compressed_size)
		self._write(fd.uncompressed_size)
		self._write(struct.pack("<H", len(filename)))
		self._write(struct.pack("<H", 0)) # Extra field len
		# self._write(fd.header_offset)
		self._write(filename.encode("utf-8"))

		self._write(data)

	def _write(self, data: bytes):
		self.input.write(data)
		self.offset += len(data)

	def close(self):
		# Build central directory headers
		cd = bytearray()

		for fd in self.files:
			cd.extend(b"\x50\x4b\x01\x02")                 # Signature
			cd.extend(self.VERSION)                        # Version
			cd.extend(self.VERSION)                        # Vers. needed
			cd.extend(fd.flags)
			cd.extend(fd.compression)
			cd.extend(fd.last_modified_time)
			cd.extend(fd.last_modified_date)
			cd.extend(fd.crc32)
			cd.extend(fd.compressed_size)
			cd.extend(fd.uncompressed_size)
			cd.extend(struct.pack("<H", len(fd.filename))) # File name len
			cd.extend(struct.pack("<H", 0))                # Extra field len
			cd.extend(struct.pack("<H", 0))                # File comment len
			cd.extend(struct.pack("<H", 0))                # Disk # start
			cd.extend(struct.pack("<H", 0))                # Internal attributes
			cd.extend(struct.pack("<I", 0))                # External attributes
			cd.extend(fd.header_offset)                    # Offset of local header
			cd.extend(fd.filename.encode("utf-8"))

		cd_size = len(cd)
		cd_offset = self.offset
		self._write(cd)

		# Build end of central directory header
		self._write(b"\x50\x4b\x05\x06")
		self._write(b"\x00\x00")           # Disk number
		self._write(b"\x00\x00")           # Disk # w/CD
		self._write(struct.pack("<H", len(self.files)))  # Disk entries
		self._write(struct.pack("<H", len(self.files)))  # Total entries
		self._write(struct.pack("<I", cd_size)) # Central directory size
		self._write(struct.pack("<I", cd_offset)) # Offset of cd wrt to starting disk
		self._write(struct.pack("<H", 0))  # Comment len

		self.eof = True

if __name__ == "__main__":
	if len(sys.argv) < 2:
		print("USAGE: python3 {} <wildcard path>".format(sys.argv[0]))
		exit(0)

	term_width = os.get_terminal_size().columns - 8

	with open("test.zip", "wb") as f:
		zipper = ZipStreamer(f)
		

		try:
			zipper.start()

			root_path = Path(sys.argv[1]).resolve()
			print(f"Zipping {root_path}")

			if root_path.is_dir():
				for dirpath, dirnames, filenames in os.walk(root_path):
					for filename in filenames:
						full_path = Path(os.path.join(dirpath, filename))
						rel_path = full_path.relative_to(root_path)
						with open(full_path, "rb") as f:
							print(f"Zipping {rel_path}")
							zipper.add_file(f, str(rel_path))
				

			# for dir_entry in os.scandir(sys.argv[1]):
			# 	if dir_entry.is_file():
			# 		print("Zipping", dir_entry.name, " " * (term_width - len(dir_entry.name)), end="\r")
			# 		with open(dir_entry.path, "rb") as f:
			# 			zipper.add_file(f, dir_entry.name)

			# for filename in iglob(sys.argv[1]):
			# 	print("Zipping", filename, end="\n")
			# 	with open(filename, "rb") as f:
			# 		zipper.add_file(f, filename)

			print("Finished zipping")
		finally:
			print("Waiting for zipper")
			zipper.close()
			zipper.join()
			print("Zipper done.")

