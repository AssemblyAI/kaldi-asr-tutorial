import reset_directory
import subprocess as s
import os
import sys
import glob


if len(sys.argv) == 1:
    try:
        FILE_NAME_WAV = glob.glob("*.wav")[0]
    except:
        raise ValueError("No .wav file in the root directory")
elif len(sys.argv) == 2:
    FILE_NAME_WAV = list(sys.argv)[1]
    if FILE_NAME_WAV[-4:] != ".wav":
        raise ValueError("Provided filename does not end in '.wav'")
else:
    raise ValueError("Too many arguments provided. Aborting")

FILE_NAME = FILE_NAME_WAV[:-4]

ORIGINAL_DIRECTORY = os.getcwd()

# Make data/test dir
os.makedirs("./data/test")
os.chdir("./data/test")

# Have my_ex folder under egs. Have this as an empty project framework (e.g. copy yesno)
# Put wav.scp, utt2spk, test, and spk2utt in this file
# Assuming one speaker,
with open("spk2utt", "w") as f:
    f.write("global {0}".format(FILE_NAME))

with open("utt2spk", "w") as f:
    f.write("{0} global".format(FILE_NAME))

wav_path = os.getcwd() + "/" + FILE_NAME_WAV
with open("wav.scp", "w") as f:
    f.write("{0} {1}".format(FILE_NAME, wav_path))

# Return to s5
os.chdir(ORIGINAL_DIRECTORY)

# Identify sample rate in the .wav file
bash_out = s.run("soxi {0}".format(FILE_NAME_WAV), stdout=s.PIPE, text=True, shell=True)
cleaned_list = bash_out.stdout.replace(" ","").split('\n')
sample_rate = [x for x in cleaned_list if x.startswith('SampleRate:')]
sample_rate = sample_rate[0].split(":")[1]

# Read mfcc congifuration file
with open("./conf/mfcc_hires.conf", "r") as mfcc:
    # Read lines of file
    lines = mfcc.readlines()
    
# Identify the line that corresponds to setting the sample frequency and isolate it
line_idx = [lines.index(l) for l in lines if l.startswith('--sample-frequency=')]
line = lines[line_idx[0]]

# Reformat the line to use the sample rate of the .wav file
line = line.split("=")
line[1] = sample_rate + line[1][line[1].index(" #"):]
line = "=".join(line)

# Replace the relevant line in `lines` and write to file
lines[line_idx[0]] = line
final_str = "".join(lines)
with open("./conf/mfcc_hires.conf", "w") as mfcc:
    mfcc.write(final_str)


with open("main_log.txt", "w") as f:
    # Copy wav file into data folder
    bash_out = s.run("cp {0} data/test/{0}".format(FILE_NAME_WAV), stdout=f, text=True, shell=True)
    
    # EXTRACT FEATURES
    # Copy data into new directory
    bash_out = s.run("utils/copy_data_dir.sh data/test data/test_hires", stdout=f, text=True, shell=True)
    # Make MFCC features using configuration file provided
    bash_out = s.run("steps/make_mfcc.sh --nj 1 --mfcc-config "
                     "conf/mfcc_hires.conf data/test_hires", stdout=f, text=True, shell=True)
    # Compute CMVN statistics
    bash_out = s.run("steps/compute_cmvn_stats.sh data/test_hires", stdout=f, text=True, shell=True)
    # Clean the directory
    bash_out = s.run("utils/fix_data_dir.sh data/test_hires", stdout=f, text=True, shell=True)

    # Download pre trained models if don't already have
    for component in ["chain", "extractor", "lm"]:
        tarball = "0013_librispeech_v1_{0}.tar.gz".format(component)
        if tarball not in os.listdir():
            bash_out = s.run('wget http://kaldi-asr.org/models/13/{0}'.format(tarball), stdout=f, text=True, shell=True)
    
    # EXTRACT PRE TRAINED MODELS
    bash_out = s.run('for f in *.tar.gz; do tar -xvzf "$f"; done', stdout=f, text=True, shell=True)

    # DECODE
    # Extract ivectors
    os.makedirs("./exp/nnet3_cleaned/ivectors_test_hires")
    bash_out = s.run("steps/online/nnet2/extract_ivectors_online.sh --nj 1 "
                     "data/test_hires exp/nnet3_cleaned/extractor exp/nnet3_cleaned/ivectors_test_hires",
                     stdout=f, text=True, shell=True)

    # Create decoding graph using the small trigram language model
    os.makedirs("./exp/chain_cleaned/tdnn_1d_sp/graph_tgsmall")
    bash_out = s.run("utils/mkgraph.sh --self-loop-scale 1.0 --remove-oov "
                     "data/lang_test_tgsmall exp/chain_cleaned/tdnn_1d_sp exp/chain_cleaned/tdnn_1d_sp/graph_tgsmall",
                     stdout=f, text=True, shell=True)

    # Decode using the created graph
    os.makedirs("./exp/chain_cleaned/tdnn_1d_sp/decode_test_tgsmall")
    bash_out = s.run("steps/nnet3/decode.sh --acwt 1.0 --post-decode-acwt 10.0 --nj 1 "
                     "--online-ivector-dir exp/nnet3_cleaned/ivectors_test_hires "
                     "exp/chain_cleaned/tdnn_1d_sp/graph_tgsmall "
                     "data/test_hires exp/chain_cleaned/tdnn_1d_sp/decode_test_tgsmall",
                     stdout=f, text=True, shell=True)

    # Enter decode directory
    os.chdir("./exp/chain_cleaned/tdnn_1d_sp/decode_test_tgsmall")
    # Unzip
    bash_out = s.run("gunzip -k lat.1.gz", stdout=f, text=True, shell=True)
    # Return to root directory
    os.chdir(ORIGINAL_DIRECTORY)

    # GET TRANSCRIPTION
    command = "../../../src/latbin/lattice-best-path " \
              "ark:'gunzip -c exp/chain_cleaned/tdnn_1d_sp/decode_test_tgsmall/lat.1.gz |' " \
              "'ark,t:| utils/int2sym.pl -f 2- " \
              "{0}/exp/chain_cleaned/tdnn_1d_sp/graph_tgsmall/words.txt > out.txt'".format(ORIGINAL_DIRECTORY)
    bash_out = s.run(command, stdout=f, text=True, shell=True)

    # RESCORE
    command = "../../../scripts/rnnlm/lmrescore_pruned.sh --weight 0.45 --max-ngram-order 4 " \
              "data/lang_test_tgsmall exp/rnnlm_lstm_1a data/test_hires " \
              "exp/chain_cleaned/tdnn_1d_sp/decode_test_tgsmall exp/chain_cleaned/tdnn_1d_sp/decode_test_rescore"
    bash_out = s.run(command, stdout=f, text=True, shell=True)

    command = "../../../src/latbin/lattice-best-path " \
              "ark:'gunzip -c exp/chain_cleaned/tdnn_1d_sp/decode_test_rescore/lat.1.gz |' " \
              "'ark,t:| utils/int2sym.pl -f 2- " \
              "{0}/exp/chain_cleaned/tdnn_1d_sp/graph_tgsmall/words.txt > out_rescore.txt'".format(ORIGINAL_DIRECTORY)
    bash_out = s.run(command, stdout=f, text=True, shell=True)
    
