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

for file in ["chain", "extractor", "lm"]:
	try:
		os.remove("0013_librispeech_v1_{0}.tar.gz".format(file))
	except:
		pass		
