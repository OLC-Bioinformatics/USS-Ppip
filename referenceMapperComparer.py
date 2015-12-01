# Import the necessary modules
# OS is used for file/folder manipulations
import os
# Subprocess->call is used for making system calls
import subprocess
# Errno is used in the file creation command  - I think it's similar to the $! variable in Perl
import errno
# Glob finds all the path names matching a specified pattern according to the rules used by the Unix shell
from glob import glob
# Shutil is useful for file moving/copying
import shutil
# Regex
import re
# System tools
import sys
# Can import date, and calculate length of run, etc.
import time
# Multiprocessing module
from multiprocessing import Pool
# JSON module for reading and printing variables in .json format
import json
# Default dictionaries allow nested dictionaries
from collections import defaultdict
# Import custom modules
import SMALTcombined
import SMALT
import bamProcessorCombined
import bamProcessor
import rawMLST
import bamPysamStats
import bamPysamStatsCombined
import fastqCreator

# Argument parser for user-inputted values, and a nifty help menu
from argparse import ArgumentParser

__author__ = 'akoziol'

# Parser for arguments
parser = ArgumentParser(description='Perform modelling of parameters for GeneSipping')
parser.add_argument('-v', '--version', action='version', version='%(prog)s v1.0')
parser.add_argument('-p', '--path', required=True, help='Specify input directory')
parser.add_argument('-s', '--sequencepath', required=True, help='Path of .fastq(.gz) files to process. If not '
                    'provided, the default path of "path/sequences" will be used')
parser.add_argument('-t', '--targetpath', required=False, help='Path of target files to process. If not '
                    'provided, the default path of "path/targets" will be used')
parser.add_argument('-m', '--miSeqPath', required=False, help='Path of the folder containing MiSeq run data folder')
parser.add_argument('-f', '--miseqfolder', required=False, help='Name of the folder containing MiSeq run data')
parser.add_argument('-r1', '--readLengthForward', required=False, help='Length of forward reads to use. Can specify'
                    '"full" to take the full length of forward reads specified on the SampleSheet')
parser.add_argument('-r2', '--readLengthReverse', required=False, default=0, help='Length of reverse reads to use. '
                    'Can specify "full" to take the full length of reverse reads specified on the SampleSheet')
parser.add_argument('-c', '--customSampleSheet', required=False, help='Path of folder containing a custom sample '
                    'sheet (still must be named "SampleSheet.csv")')
parser.add_argument('-P', '--projectName', required=False, help='A name for the analyses. If nothing is provided, then '
                    'the "Sample_Project" field in the provided sample sheet will be used. Please note that bcl2fastq '
                    'creates subfolders using the project name, so if multiple names are provided, the results will be '
                    'split as into multiple projects')

# Get the arguments into a list
args = vars(parser.parse_args())

# Define variables from the arguments - there may be a more streamlined way to do this
path = os.path.join(args['path'], "")

# Optional arguments. If these paths are present, add a trailing "/" with os.path.join
if args['miSeqPath']:
    miseqpath = os.path.join(args['miSeqPath'], "")
else:
    miseqpath = ""
if args['customSampleSheet']:
    customsamplesheet = os.path.join(args['customSampleSheet'], "")

# If these variables are not defined, set to default values. I chose to set the default values this way rather than
# specifying default=... in the parser.add_argument because I need to use variables that were defined following the
# argument parsing
if args['sequencepath']:
    sequencepath = os.path.join(args['sequencepath'], "")
else:
    sequencepath = "%ssequences/" % path

if args['targetpath']:
    targetpath = os.path.join(args['targetpath'], "")
else:
    targetpath = "%stargets/" % path

# Raw read sipping arguments
miseqfolder = args['miseqfolder']
projectname = args['projectName']
forwardreads = args['readLengthForward']
reversereads = args['readLengthReverse']


def make_path(inpath):
    """
    from: http://stackoverflow.com/questions/273192/check-if-a-directory-exists-and-create-it-if-necessary \
    does what is indicated by the URL
    :param inpath: string of the supplied path
    """
    try:
        # os.makedirs makes parental folders as required
        os.makedirs(inpath)
    # Except os errors
    except OSError as exception:
        # If the os error is anything but directory exists, then raise
        if exception.errno != errno.EEXIST:
            raise


def make_dict():
    """Makes Perl-style dictionaries"""
    return defaultdict(make_dict)

# Initialise the dictionary responsible for storing the report data
metadatafile = defaultdict(make_dict)

# Define global variables
seqdict = defaultdict(make_dict)
reportfolder = ""
# Initialise the count used in the dotter function
count = 0


def dotter():
    """Prints formatted time to stdout at the start of a line, as well as a "."
    whenever the length of the line is equal or lesser than 80 "." long"""
    # Use a global variable
    global count
    if count <= 80:
        sys.stdout.write('.')
        count += 1
    else:
        sys.stdout.write('\n[%s] .' % (time.strftime("%H:%M:%S")))
        count = 1


def printtime(string):
    """Prints a string in bold with the elapsed time
    :param string: a string to be printed in bold
    """
    global start
    print '\n\033[1m' + "[Elapsed Time: %0.2f seconds] %s" % (time.time() - start, string) + '\033[0m'


def foldererprepprocesses(samplename):
    """
    A helper function to make a pool of processes to allow for a multi-processed approach to error correction
    :param samplename: string of the name of the strain to decompress
    """
    global sequencepath
    print "Decompressing .gz files"
    # Initialise variables
    foldererprepargs = []
    createfoldererpool = Pool()
    # Prepare a tuple of the argument (name)
    for name in samplename:
        foldererprepargs.append(name)
    # This map function allows for multi-processing
    createfoldererpool.map(folderer, foldererprepargs)


def folderer(gzfile):
    """
    Uses gzip to decompress .gz.fastq files
    :param gzfile: string of file name and path of a gzipped file
    """
    # Define the gzip command line call
    gzipcommand = "gzip -d --force %s" % gzfile
    # Run the call
    subprocess.call(gzipcommand, shell=True, stdout=open(os.devnull, 'wb'), stderr=open(os.devnull, 'wb'))
    dotter()


def filer(filelist):
    """
    Helper script that creates a set of the stain names created by stripping off parts of the filename.
    Hopefully handles different naming conventions (e.g. 2015-SEQ-001_S1_L001_R1_001.fastq(.gz),
    2015-SEQ-001_R1_001.fastq.gz, 2015-SEQ-001_R1.fastq.gz, 2015-SEQ-001_1.fastq.gz, and 2015-SEQ-001_1.fastq.gz
    all become 2015-SEQ-001)
    :param filelist:
    """
    # Initialise the set
    fileset = set()
    for seqfile in filelist:
        # Search for the conventional motifs present following strain names
        # _S\d+_L001_R\d_001.fastq(.gz) is a typical unprocessed Illumina fastq file
        if re.search("_S\d+_L001", seqfile):
            fileset.add(re.split("_S\d+_L001", seqfile)[0])
        # Files with _R\d_001.fastq(.gz) are created in the SPAdes assembly pipeline
        elif re.search("_R\d_001", seqfile):
            fileset.add(re.split("_R\d_001", seqfile)[0])
        # _R\d.fastq(.gz) represents a simple naming scheme for paired end reads
        elif re.search("R\d.fastq", seqfile):
            fileset.add(re.split("_R\d.fastq", seqfile)[0])
        # _\d.fastq is always possible
        elif re.search("[-_]\d.fastq", seqfile):
            fileset.add(re.split("[-_]\d.fastq", seqfile)[0])
        # .fastq is the last option
        else:
            fileset.add(re.split(".fastq", seqfile)[0])
        dotter()
    return fileset


def nameextractor():
    """Creates a set of the names of the files to be used in the analyses"""
    global sequencepath
    fileset = set()
    foldernames = set()
    filefull = []
    # Create lists of the .gz, the .fastq, and the folders in the path
    gzchecker = glob("%s*.gz" % sequencepath)
    # Extracts the .gz files as required
    if gzchecker:
        foldererprepprocesses(gzchecker)
    fastqchecker = glob("%s*.fastq" % sequencepath)
    # For each list, ensure that the list exists...
    if fastqchecker:
        # Create appropriately named folders and move the .fastq files into the proper folder
        filelist, foldernames, filefull = seqmovr(fastqchecker)
    folderchecker = glob("%s*/" % sequencepath)
    # Get folder names in the sequences folder - this should only be useful if there were some files
    # in folders, and some not in folders
    if folderchecker:
        for seqname in folderchecker:
            filefull = []
            # Add the appropriate variables to the appropriate sets
            fileset.add(seqname)
            foldernames.add(os.path.split(seqname)[0].split("/")[-1])
            for fastqfile in glob("%s/*.fastq" % seqname):
                # Baited files shouldn't be added to the list now.
                if not re.search("bait_match", fastqfile):
                    filefull.append(fastqfile)
            dotter()
            #  Add the unique fastq files to the dictionary
            fastqfnr = []
            foldername = os.path.split(seqname)[0].split("/")[-1]
            for files in filefull:
                # Use fileR to determine the "short (and unique) file name"
                filename = filer([os.path.basename(files)]).pop()
                # If these variables are identical, add the file to the list
                if foldername == filename:
                    fastqfnr.append(files)
                # Add the list to the dictionary
                seqdict[foldername]["rawFastq"] = sorted(fastqfnr)
    # Return the lists of path/folder names and folder names
    return list(fileset), list(foldernames), filefull


def seqmovr(seqfull):
    """
    Creates appropriately named folders, and moves sequence files to appropriate folders
    :param seqfull: list of all strains in the analysis
    """
    global sequencepath, count
    count = 0
    foldernames = set()
    filefull = []
    # Extract the unique names using the helper function fileR...
    filelist = filer(seqfull)
    # Create the folders if necessary
    print "\nMoving files to appropriate folders"
    for folder in filelist:
        # There can be an empty string in this set (''), which breaks the loop
        if folder:
            # Split the path from the folders - will give a name like 2015-SEQ-794
            foldername = os.path.split(folder)[-1]
            foldernames.add(foldername)
            #  Make folders as necessary
            make_path(folder)
            # Search the path for any file or folder that contains the seqName
            filecheck = [f for f in os.listdir(sequencepath) if re.search(foldername, f)]
            for seqfile in filecheck:
                # Use fileR to determine the "short" name of the sequence file
                seqset = filer([seqfile]).pop()
                # Move files (ignore folders) if folderName identical to the "short" file name
                if os.path.isfile("%s%s" % (sequencepath, seqfile)) and foldername == seqset:
                    shutil.move("%s%s" % (sequencepath, seqfile), "%s%s/%s" % (sequencepath, foldername, seqfile))
                    filefull.append("%s%s/%s" % (sequencepath, foldername, seqfile))
    return filelist, foldernames, filefull


def baitrprocesses(analysistype):
    """
    Baiting multiprocessing helper function
    :param analysistype: string of the analysis type
    """
    global seqdict
    # Initialise the args list
    baitargs = []
    # Initialise the pool of processes - it defaults to the number of processors
    baitpool = Pool()
    for foldername in seqdict:
        baittype = seqdict[foldername]["bait"]["fastqFiles"]
        # Iterate through the different bait types stored in the dictionary
        for btype in baittype.keys():
            #  Only perform the baiting for the current analysis type
            if analysistype in btype:
                # Append the appropriate variables
                baitargs.append((seqdict[foldername]["bait"]["fastqFiles"][btype], 
                                 seqdict[foldername]["rawFastq"], btype))
    # Map the baitArgs to the baitR function
    folderpath = (baitpool.map(baitr, baitargs))
    # Repopulate the sequence dictionary with the new bait files
    for folder in folderpath:
        foldername = os.path.split(os.path.split(folder)[0])[1]
        baitmatch = glob("%s/*.fastq" % folder)
        baittype = seqdict[foldername]["bait"]["fastqFiles"].keys()[0]
        seqdict[foldername]["bait"]["fastqFiles"][baittype] = baitmatch


def baitr((baitfile, sequences, baittype)):
    """Runs mirabait with selected targets on fastq files"""
    global targetpath
    # Works on paired-end and unpaired-end reads
    if len(sequences) == 2:
        # Define the forward and reverse .fastq reads based on their position in the (ordered) list
        forwardfastqpath = sequences[0]
        reversefastqpath = sequences[1]
        # Get the path of the fastq files
        baitpath = os.path.split(forwardfastqpath)[0] + "/%s" % baittype
        # Create the path (if necessary)
        make_path(baitpath)
        baitcheck = glob("%s/%s_match*" % (baitpath, baittype))
        # Check to see if the baiting process has been performed previously
        if len(baitcheck) < 2:
            # Define the baiting command - if a hash of the target has previously been computed and placed in the
            # bait folder, then proceed appropriately
            if ".gz" in baitfile:
                baitcommand = "cd %s && mirabait -L %s -N %s -p %s %s" \
                              % (baitpath, baitfile, baittype, forwardfastqpath, reversefastqpath)
                # Define /dev/null
                fnull = open(os.devnull, 'wb')
                # Run the command
                subprocess.call(baitcommand, shell=True, stdout=fnull, stderr=fnull)
            else:
                baitcommand = "cd %s && mirabait -b %s -N %s -p %s %s" \
                              % (baitpath, baitfile, baittype, forwardfastqpath, reversefastqpath)
                # Move the newly created hashstat file to the bait folder
                baithash = "%s/hashstat.mhs.gz" % baitpath
                hashdestination = baitfile.split(".")[0] + ".mhs.gz"
                # Define /dev/null
                fnull = open(os.devnull, 'wb')
                # Run the command
                subprocess.call(baitcommand, shell=True, stdout=fnull, stderr=fnull)
                # Try to move the baitHash file to the bait path, but pass on failure
                try:
                    shutil.move(baithash, hashdestination)
                except IOError:
                    pass
    else:
        # Define the forward and reverse .fastq reads based on their position in the (ordered) list
        forwardfastqpath = sequences[0]
        # Get the path of the fastqfiles
        baitpath = os.path.split(forwardfastqpath)[0] + "/%s" % baittype
        make_path(baitpath)
        baitcheck = glob("%s/%s_match*" % (baitpath, baittype))
        if not baitcheck:
            # Define the baiting command
            if ".gz" in baitfile:
                baitcommand = "cd %s && mirabait -L %s -N %s %s" % (baitpath, baitfile, baittype, forwardfastqpath)
                # Define /dev/null
                fnull = open(os.devnull, 'wb')
                # Run the command
                subprocess.call(baitcommand, shell=True, stdout=fnull, stderr=fnull)
            else:
                baitcommand = "cd %s && mirabait -b %s -N %s %s" % (baitpath, baitfile, baittype, forwardfastqpath)
                # Move the newly created hashstat file to the bait folder
                # print baitCommand
                baithash = "%s/hashstat.mhs.gz" % baitpath
                hashdestination = baitfile.split(".")[0] + ".mhs.gz"
                # Define /dev/null
                fnull = open(os.devnull, 'wb')
                # Run the command
                subprocess.call(baitcommand, shell=True, stdout=fnull, stderr=fnull)
                try:
                    shutil.move(baithash, hashdestination)
                except IOError:
                    pass
    dotter()
    return baitpath


def sixteensreportmaker(resultdict, analysistype):
    """
    Creates reports for 16S analyses
    :param resultdict: dictionary containing results of 16S analyses
    :param analysistype: string of the analysis type
    """
    global reportfolder, seqdict
    # Create the name for the report folder - this variable will be passed on to other functions
    reportfolder = "%sreports/%s" % (path, time.strftime("%Y.%m.%d.%H.%M.%S"))
    # Create the path if necessary
    make_path(reportfolder)
    # Initialise variables
    compiledresultstring = ""
    csvheader = ""
    # Iterate through each strain in resultDict
    for strain in resultdict:
        # Create variables as required
        baittype = seqdict[strain]["bait"]["fastqFiles"].keys()[0]
        fastqdir = os.path.split(seqdict[strain]["bait"]["fastqFiles"][baittype][0])[0]
        reportdir = "%s/reports" % fastqdir
        # Create a strain-specific report in the <strain>/16S/reports directory
        reportname = "%s/%s_%s_reports.tsv" % (reportdir, strain, baittype)
        make_path(reportdir)
        csvfile = open(reportname, "wb")
        # Get the header started
        csvheader = "Strain,Genus,Accession,PercentIdentity,AvgFoldCov\n"
        # Initialise the variable to hold the result data
        resultstring = ""
        # The results are stored in a nested dictionary
        for genus in resultdict[strain]:
            for database in resultdict[strain][genus]:
                for accession in resultdict[strain][genus][database]:
                    for avgidentity, avgfoldcov in resultdict[strain][genus][database][accession].iteritems():
                        resultstring = "%s,%s,%s,%s,%s" % (strain, genus, accession, avgidentity, avgfoldcov)
                        compiledresultstring += "%s,%s,%s,%s,%s\n" % (strain, genus, accession, avgidentity, avgfoldcov)
        # Write the header and data strings to file
        csvfile.write(csvheader)
        csvfile.write(resultstring)
        csvfile.close()
    # Create a report containing all the 16S results from each strain
    compiledcsvfile = open("%s/%s_results.tsv" % (reportfolder, analysistype), "wb")
    # Write the header and data strings to file
    compiledcsvfile.write(csvheader)
    compiledcsvfile.write(compiledresultstring)
    compiledcsvfile.close()


def pathoreportr(matchdict, analysistype, organismdict, organismlist):
    """
    Creates reports for pathotyping and serotyping results
    :param matchdict: dictionary of hits of a strain to targets
    :param analysistype: string of the analysis type
    :param organismdict: dictionary of the 16S results
    :param organismlist: list of all the genera in the current analysis
    """
    global reportfolder, seqdict
    # Initialise data string
    completestring = ""
    # Iterate through the genera present in the analyses
    for organism in organismlist:
        # Initialise variables
        orgcount = 0
        organismdata = ""
        organismheader = "Strain,Genus,"
        # Iterate through all the strains in the analysis
        for strain in seqdict:
            # Try/except for attribute errors - if a strain does not have results, then just pass
            try:
                strainheader = "Strain,"
                straindata = ""
                # Iterate through the organisms in organismdict
                for currentorganism in organismdict[strain]:
                    # If this current organism matches the organism of interest, proceed
                    if organism == currentorganism:
                        # Increment orgcount
                        orgcount += 1
                        headergenes = ''
                        # Iterate through the targets to find the names of the genes for the headers
                        for target in sorted(seqdict[strain]["targets"][analysistype]):
                            # Set target name
                            targetname = os.path.basename(target).split(".")[0]
                            headergenes += "%s," % targetname
                        # As the header and data variables are strings, the header information only needs to be appended
                        # once, otherwise, the header would preceed the data for every strain
                        if orgcount == 1:
                            organismheader += headergenes
                            completestring += "Strain,Genus,"
                            completestring += headergenes
                        # Strain header is unique for each strain, so it should be populated every time
                        strainheader += headergenes
                        # Populate the data strings with the appropriate variables
                        organismdata += "\n%s,%s," % (strain, organism)
                        completestring += "\n%s,%s," % (strain, organism)
                        # Organism is not necessary for the strain-specific reports
                        straindata += "\n%s," % strain
                        # Iterate through the targets to find the presence/absence of each target
                        for target in sorted(seqdict[strain]["targets"][analysistype]):
                            targetname = os.path.basename(target).split(".")[0]
                            # If there is a result for a strain/target combination
                            if matchdict[strain][targetname]:
                                # Pathotype results are treated slightly differently than serotyping results
                                if analysistype == "pathotype":
                                    # Populate the strings with positive results ("+")
                                    completestring += "+,"
                                    organismdata += "+,"
                                    straindata += "+,"
                                else:
                                    # Serotyping is not a binary presence/absence. The calculated serotype is reported
                                    serotype = matchdict[strain][targetname].keys()[0].split("_")[-1]
                                    # Populate the strings with the serotype
                                    completestring += "%s," % serotype
                                    organismdata += "%s," % serotype
                                    straindata += "%s," % serotype
                            # If there is no strain/target result, populate the strings with negative results ("-")
                            else:
                                completestring += "-,"
                                organismdata += "-,"
                                straindata += "-,"
                    # Pull values from seqdict in order to create properly named reports in the appropriate folders
                    baittype = seqdict[strain]["bait"]["fastqFiles"].keys()[0]
                    fastqdir = os.path.split(seqdict[strain]["bait"]["fastqFiles"][baittype][0])[0]
                    reportdir = "%s/reports" % fastqdir
                    reportname = "%s/%s_%s_reports.csv" % (reportdir, strain, baittype)
                    make_path(reportdir)
                    # Open the strain-specific report, and write the appropriate header/results
                    straincsvfile = open(reportname, "wb")
                    straincsvfile.write(strainheader)
                    straincsvfile.write(straindata)
                    straincsvfile.close()
                # Create the organism-specific report, and write the appropriate header/results
                organismcsvfile = open("%s/%s_%s_results.csv" % (reportfolder, analysistype, organism), "wb")
                organismcsvfile.write(organismheader)
                organismcsvfile.write(organismdata)
                organismcsvfile.close()
            # If there are no pathotyping/serotyping results for a particular strain, pass
            except AttributeError:
                pass
        # Add a newline character to completestring for each strain
        completestring += "\n"
    # Create the report for each strain in the data set, and write the appropriate header/results
    compiledcsvfile = open("%s/%s_results.csv" % (reportfolder, analysistype), "wb")
    compiledcsvfile.write(completestring)
    compiledcsvfile.close()


def baittargets(currenttargetpath, analysistype):
    """
    Creates a file to be used for baiting if one does not already exist by concatenating together all individual
    target files in the current target path
    :param currenttargetpath: path of the targets in the current analysis
    :param analysistype: string of the current analysis type
    """
    if not os.path.isfile("%s/bait/%sBait.fa" % (currenttargetpath, analysistype)):
        # Creates the bait path if necessary
        make_path("%s/bait" % currenttargetpath)
        # Make a list of all the target files
        targetfiles = glob("%s/*.*fa*" % currenttargetpath)
        # List comprehension to remove faidx processed target files with the format .fa.fai
        targetfiles = [target for target in targetfiles if ".fai" not in target]
        # Iterate through the filtered list
        for tfile in targetfiles:
            # Open the bait file
            with open("%s/bait/%sBait.fa" % (currenttargetpath, analysistype), "ab") as bait:
                # Create a handle for each target file
                with open(tfile, "rb") as targetf:
                    # Use shutil.copyfileobj to concatenate all files together
                    shutil.copyfileobj(targetf, bait)


def sixteens():
    """Performs the necessary analyses on strains using 16S targets"""
    global targetpath, seqdict
    # Set the analysis type variable to 16S. This variable is important for retrieving 16S-specific data from seqdict
    analysistype = "16S"
    # Set the path of the analysistype data
    currenttargetpath = "%s%s" % (targetpath, analysistype)
    # Create the bait target file (if necessary)
    baittargets(currenttargetpath, analysistype)
    # In order to save time, during baiting, a precomputed hash file is used
    hashfile = glob("%s/bait/*.gz" % currenttargetpath)
    # If the hashfile is present, use it
    if hashfile:
        baitfile = hashfile[0]
    # Otherwise, use the concatenated bait file
    else:
        baitfile = glob("%s/bait/*.fa*" % currenttargetpath)[0]
    print "Filtering .fastq files with %s targets" % analysistype
    # Get a list of the targets into a variable
    sixteensdatabase = glob("%s/*.fa*" % currenttargetpath)
    # Filter as above - repeated as the above code is not executed if the bait file is already present
    sixteensdatabase = [target for target in sixteensdatabase if ".fai" not in target]
    # Populate seqdict with the name and path of the bait file used as well as the database
    for foldername in seqdict:
        seqdict[foldername]["bait"]["fastqFiles"][analysistype] = baitfile
        seqdict[foldername]["targets"][analysistype] = sixteensdatabase
    # Run the baiting process
    baitrprocesses(analysistype)
    # Perform SMALT indexing of targets
    print "\nIndexing %s targets" % analysistype
    SMALT.smaltindextargetsprocesses(sixteensdatabase, currenttargetpath)
    # Perform reference mapping with SMALT
    print '\nPerforming %s reference mapping' % analysistype
    SMALT.smaltmappingprocesses(seqdict, analysistype, "SMALT")
    # Use samtools to sort the bam files
    print "\nSorting mapped %s files" % analysistype
    bamProcessor.sortingprocesses(seqdict, analysistype)
    # Use samtools to index the sorted bam files
    print '\nIndexing sorted %s files' % analysistype
    bamProcessor.bamindexingprocesses(seqdict, analysistype)
    # Use pysamstats to parse the sorted, indexed bam files
    print '\nParsing %s results' % analysistype
    generadict, generalist = bamPysamStats.bamparseprocesses(seqdict, analysistype)
    # Create reports of the results
    sixteensreportmaker(generadict, analysistype)
    # Return the computed genera
    return generadict, generalist


def mlst(organismdict, organismlist):
    """
    Performs the necessary analyses on strains using genus-specific MLST targets
    :param organismdict: dictionary of the 16S results
    :param organismlist: list of all the genera in the current analysis
    """
    global targetpath, seqdict
    # Set the analysis type
    analysistype = "MLST"
    profiletype = "MLSTprofile"
    # MLST targets are stored in targetpath/Organism/<genus>/MLST/alleles
    currenttargetpath = "%sOrganism" % targetpath
    # Print this out before the loop
    print '\nIndexing %s target files' % analysistype
    for strain in organismdict:
        # If there is not an MLST scheme installed for a particular organism, then the script will crash when it tries
        # to find the necessary files, as they are not present. Allow index errors to pass
        try:
            # Using the organismdict entry (genus) generated in the 16S analysis, set the allele and profile paths
            # NB: This will come up multiple times with this script, but I only allowed a small amount of freedom in
            # the placement of folders. Usually, there are strict folder hierarchies, which must be followed
            mlstpath = glob("%s/%s/*MLST*" % (currenttargetpath, organismdict[strain].keys()[0]))[0] + "/alleles"
            profilepath = glob("%s/%s/*MLST*" % (currenttargetpath, organismdict[strain].keys()[0]))[0] + "/profile"
            # Try to find the precomputed .json profile file
            profilefile = glob("%s/*.json" % profilepath)
            # If it does not exist, find the .txt profile file. As the script requires a small amount of formatting on
            # the profile file prior to analysis, I forced a changed in file extension to hopefully ensure that this
            # formatting has been performed
            if not profilefile:
                profilefile = glob("%s/*.txt" % profilepath)[0]
            else:
                profilefile = profilefile[0]
            # Create the bait target file (if necessary)
            baittargets(currenttargetpath, analysistype)
            # If a precomputed hash file is present in the bait folder, use it to save on processing time
            hashfile = glob("%s/bait/*.gz" % mlstpath)
            if hashfile:
                baitfile = hashfile[0]
            # Otherwise, use the .fasta bait file created above
            else:
                baitfile = glob("%s/bait/*.fa*" % mlstpath)[0]
            # Set the bait type variable using the genus of the strain and the analysis type
            baittype = "%s_MLST" % organismdict[strain].keys()[0]
            # Store the baittype variable in seqdict
            seqdict[strain]["bait"]["fastqFiles"][baittype] = baitfile
            # Get the targets into a list
            targets = glob("%s/*.*fa" % mlstpath)
            # Remove faidx processed files
            targets = [target for target in targets if ".fai" not in target]
            # Store the target list, and the profile file in seqdict
            seqdict[strain]["targets"][analysistype] = targets
            seqdict[strain]["MLSTprofile"] = profilefile
            # Index the SMALT targets
            SMALT.smaltindextargetsprocesses(targets, mlstpath)
        except IndexError:
            pass
    # Bait!
    print "Filtering .fastq files with %s targets" % analysistype
    baitrprocesses(analysistype)
    # Get the MLST profile into a dictionary
    print "\nLoading %s profiles" % analysistype
    profiledict, genedict = rawMLST.profilR(seqdict, profiletype)
    print '\nPerforming %s reference mapping' % analysistype
    # Perform SMALT reference mapping
    SMALT.smaltmappingprocesses(seqdict, analysistype, "SMALT")
    print "\nSorting mapped %s files" % analysistype
    # Use samtools to sort reference mapped bam files
    bamProcessor.sortingprocesses(seqdict, analysistype)
    print '\nIndexing sorted %s files' % analysistype
    # Use samtools to index sorted reference mapped bam files
    bamProcessor.bamindexingprocesses(seqdict, analysistype)
    print '\nParsing %s results' % analysistype
    # Use pysamstats to parse indexed sorted reference mapped bam files
    mlstmatches = bamPysamStats.bamparseprocesses(seqdict, analysistype)
    print '\nFinding multilocus sequence types'
    # Determine sequence types
    sequencetypes = rawMLST.sequenceTyper(mlstmatches, profiledict, genedict)
    # Create a report
    rawMLST.MLSTreportMaker(seqdict, sequencetypes, analysistype, reportfolder, organismdict, organismlist, path)


def pathotyper(organismdict, organismlist, analysistype):
    """
    Performs the necessary analyses on strains using genus-specific pathotype/serotype targets
    :param organismdict: dictionary of the 16S results
    :param organismlist: list of all the genera in the current analysis
    :param analysistype: string of the current analysis type
    """
    global targetpath, seqdict
    # Targets are stored in targetpath/Organism/<genus>/<analysistype>/
    currenttargetpath = "%sOrganism" % targetpath
    # Print this prior to the loop
    print '\nIndexing %s target files' % analysistype
    # As strains will be processed depending differently based on their genus, they must be processed separately
    for strain in organismdict:
        # Try/except account for genera without pathotyping schemes
        try:
            # Set the target path
            pathopath = glob("%s/%s/%s" % (currenttargetpath, organismdict[strain].keys()[0], analysistype))[0]
            # Create the bait targets if necessary
            baittargets(pathopath, analysistype)
            # The cat file will be used in the "combined" reference mapping
            catfile = "%s/%sConcatenated.fasta" % (pathopath, analysistype)
            # If the cat file does not exist, copy the bait file from the bait folder to the target folder
            if not os.path.isfile(catfile):
                shutil.copyfile("%s/bait/%sBait.fa" % (pathopath, analysistype), catfile)
            # Find the files to be used in baiting - if a precomputed hash file is present, use it
            hashfile = glob("%s/bait/*.gz" % pathopath)
            if hashfile:
                baitfile = hashfile[0]
            else:
                baitfile = glob("%s/bait/*.fa*" % pathopath)[0]
            # Set the baittype variable as the genus, and the analysis type
            baittype = "%s_%s" % (organismdict[strain].keys()[0], analysistype)
            # Get all the targets into a list
            # Even though the cat file will be used for the reference mapping rather than the individual target files,
            # the target names (taken from the name of the target files) is still used in the parsing of results
            targets = glob("%s/*.fa*" % pathopath)
            # Remove faidx processed files from the list
            targets = [target for target in targets if ".fai" not in target and "Concatenated" not in target]
            # Add the bait file, the cat file, and the list of targets to seqdict
            seqdict[strain]["bait"]["fastqFiles"][baittype] = baitfile
            seqdict[strain]["targets"][analysistype] = targets
            seqdict[strain]["concatenatedTargets"][analysistype] = catfile
            # Index the SMALT targets
            SMALTcombined.SMALTindexTargets(catfile, pathopath)
        except IndexError:
            pass
    # Bait!
    print "Filtering .fastq files with %s targets" % analysistype
    baitrprocesses(analysistype)
    print '\nPerforming reference mapping'
    # Use SMALT to perform reference mapping
    SMALTcombined.SMALTmappingProcesses(seqdict, analysistype, "SMALT")
    print '\nSorting mapped %s files' % analysistype
    # Use samtools to sort bam files
    bamProcessorCombined.sortingprocesses(seqdict, analysistype)
    print '\nIndexing sorted %s files' % analysistype
    # Use samtools to index sorted bam files
    bamProcessorCombined.bamindexingprocesses(seqdict, analysistype)
    print '\nParsing %s results' % analysistype
    # Use pysamstats to parse results
    pathomatches = bamPysamStatsCombined.bamParseProcesses(seqdict, analysistype, reportfolder)
    # Create a report
    pathoreportr(pathomatches, analysistype, organismdict, organismlist)


def armi():
    """Performs the necessary analyses on strains using armi targets"""
    global targetpath, seqdict
    # Set the analysis type
    analysistype = "armi"
    # Set the path of the target files
    currenttargetpath = "%s%s" % (targetpath, analysistype)
    # Create the bait files as necessary
    baittargets(currenttargetpath, analysistype)
    # The cat file is all the target files concatenated together
    catfile = "%s/%sConcatenated.fasta" % (currenttargetpath, analysistype)
    # If the cat file doesn't exist, create it from the bait file generated in baittargets()
    if not os.path.isfile(catfile):
        shutil.copyfile("%s/bait/%sBait.fa" % (currenttargetpath, analysistype), catfile)
    # In order to save time, a precomputed hash file is used
    hashfile = glob("%s/bait/*.gz" % currenttargetpath)
    # If this precomputed hash exists, use it
    if hashfile:
        baitfile = hashfile[0]
    # Otherwise use the .fasta bait file
    else:
        baitfile = glob("%s/bait/*.fa*" % currenttargetpath)[0]
    # Get the full target database into a variable
    armidatabase = glob("%s/*.fa*" % currenttargetpath)
    # Filter faidx processed targets from the list
    armidatabase = [target for target in armidatabase if ".fai" not in target and "Concatenated" not in target]
    # Add necessary variables to seqdict
    for folderName in seqdict:
        seqdict[folderName]["bait"]["fastqFiles"][analysistype] = baitfile
        seqdict[folderName]["targets"][analysistype] = armidatabase
        seqdict[folderName]["concatenatedTargets"][analysistype] = catfile
    print "Filtering .fastq files with %s targets" % analysistype
    # Run the baiting process
    baitrprocesses(analysistype)
    print "\nIndexing %s targets" % analysistype
    # Index the combined target file
    SMALTcombined.SMALTindexTargets(catfile, currenttargetpath)
    print '\nPerforming %s reference mapping' % analysistype
    # Use SMALT to perform reference mapping of the combined target file
    SMALTcombined.SMALTmappingProcesses(seqdict, analysistype, "SMALT")
    print "\nSorting mapped %s files" % analysistype
    # Use samtools to sort the bam file
    bamProcessorCombined.sortingprocesses(seqdict, analysistype)
    print '\nIndexing sorted %s files' % analysistype
    # Use samtools to index the sorted bam file
    bamProcessorCombined.bamindexingprocesses(seqdict, analysistype)
    print '\nParsing %s results' % analysistype
    # Use pysamstats to parse the bam files. Mike's armi module is called from within bamPysamStatsCombined
    bamPysamStatsCombined.bamParseProcesses(seqdict, analysistype, reportfolder)


def rmlst():
    """Performs the necessary analyses on strains using armi targets"""
    global targetpath, seqdict
    # Set the analysis type
    analysistype = "rMLST"
    # Set the profile name
    profiletype = "rMLSTprofile"
    # Set the path of the analysistype data
    currenttargetpath = "%s%s" % (targetpath, analysistype)
    # Set the allele and profile path variables
    rmlstpath = currenttargetpath + "/alleles"
    rmlstprofilepath = currenttargetpath + "/profile"
    # Find the .json version of the profile file
    profilefile = glob("%s/*.json" % rmlstprofilepath)
    # If there is no .json file, use the .txt profile file instead. Note that this file must be edited (by removing
    # any columns after the last gene)
    if not profilefile:
        profilefile = glob("%s/*.txt" % rmlstprofilepath)[0]
    else:
        profilefile = profilefile[0]
    # Because the combined database of alleles is so large (~143 MB), it is filtered with uSearch prior to baiting
    # this is not done automatically, so the set-up of the bait files is slightly different here
    # In order to save time, a precomputed hash file is used
    baitfile = glob("%s/bait/*.gz" % rmlstpath)[0]
    baittargets(rmlstpath, analysistype)
    # Get the target files into a list
    targets = glob("%s/*.*fa" % rmlstpath)
    # Filter the targets
    targets = [target for target in targets if ".fai" not in target and "Concatenated" not in target]
    # Add the bait file, the profile file, and a list of the targets to seqdict
    for strain in seqdict:
        seqdict[strain]["bait"]["fastqFiles"][analysistype] = baitfile
        seqdict[strain]["targets"][analysistype] = targets
        seqdict[strain][profiletype] = profilefile
    # Index the targets
    print "\nIndexing %s targets" % analysistype
    SMALT.smaltindextargetsprocesses(targets, rmlstpath)
    # Bait!
    print "Filtering .fastq files with %s targets" % analysistype
    baitrprocesses(analysistype)
    # Get the MLST profile into a dictionary
    print "\nLoading %s profiles" % analysistype
    profiledict, genedict = rawMLST.profilR(seqdict, profiletype)
    # Use SMALT to perform reference mapping
    print '\nPerforming %s reference mapping' % analysistype
    SMALT.smaltmappingprocesses(seqdict, analysistype, "SMALT")
    # Use samtools to sort bam files
    print "\nSorting mapped %s files" % analysistype
    bamProcessor.sortingprocesses(seqdict, analysistype)
    # Use samtools to index bam files
    print '\nIndexing sorted %s files' % analysistype
    bamProcessor.bamindexingprocesses(seqdict, analysistype)
    # Use pysamstats to parse bam files
    print '\nParsing %s results' % analysistype
    mlstmatches = bamPysamStats.bamparseprocesses(seqdict, analysistype)
    # Determine sequence types
    print '\nFinding multilocus sequence types'
    sequencetypes = rawMLST.sequenceTyper(mlstmatches, profiledict, genedict)
    # Create a report
    rawMLST.rMLSTreportMaker(seqdict, sequencetypes, analysistype, reportfolder, path)


def runner():
    """Calls the geneSipping functions in the appropriate order"""
    global sequencepath, path, miseqpath, projectname, forwardreads, reversereads
    # Run the fastqCreator function if necessary
    if miseqpath:
        printtime("fastqCreator")
        fastqCreator.createFastq(miseqpath, miseqfolder, path, projectname, 
                                 forwardreads, reversereads, customsamplesheet)
    # Run name extractor to determine the name of the samples. Additionally, this function decompresses any .gz files
    print "Finding sample names"
    nameextractor()
    printtime("16S")
    organismdict, organismlist = sixteens()
    # Run MLST analyses
    printtime("MLST")
    mlst(organismdict, organismlist)
    # Perform pathotyping analyses
    printtime("pathotype")
    pathotyper(organismdict, organismlist, "pathotype")
    # Perform serotyping analyses
    printtime("serotype")
    pathotyper(organismdict, organismlist, "serotype")
    # Perform armi analyses
    printtime("armi")
    armi()
    # Perform rMLST analyses
    printtime("rMLST")
    rmlst()

# Define the start time
start = time.time()

# Run the script
runner()

# Print a bold, green exit statement
print '\033[92m' + '\033[1m' + "\nElapsed Time: %0.2f seconds" % (time.time() - start)
print json.dumps(seqdict, sort_keys=True, indent=4, separators=(',', ': '))