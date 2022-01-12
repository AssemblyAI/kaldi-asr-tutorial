import shutil
import os

# Remove exp and data folders recursively
for folder in ["exp", "data"]:
	try:
		shutil.rmtree("./{0}".format(folder))
	except:
		pass

for file in ["out", "out_rescore", "main_log"]:
	try:
		os.remove("{0}.txt".format(file))
	except:
		pass
		
