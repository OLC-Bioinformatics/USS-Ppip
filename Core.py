__author__ = 'mikeknowles'
""" This is the core script, its mission:
Retrieve genomes
This will require the user to download rMLST data
To sort rMLST results and remove closely related sequences
then to prepare the data for strain-specific probe idenification
"""

from argparse import ArgumentParser
from collections import defaultdict
from glob import glob
from USSPpip import SigSeekr
import os, shutil, json
import GeneSeekrUper as GeneSeekr
from All2AllMash import run_mash, read_mash

def retriever(genomes, output):
    if not os.path.exists(output + "Genomes"):
        os.mkdir(output + "Genomes")
    for folders in glob(genomes + "/*"): 
        if os.path.exists(folders + "/Best_Assemblies"):
            for fasta in glob(folders + "/Best_Assemblies/*"):
                shutil.copy(fasta, output + "Genomes")

def jsonUpGoer(jsonfile, markers, genomes, outdir, method):
    if os.path.isfile(jsonfile):
        genedict = json.load(open(jsonfile))
    else:
        genedict = GeneSeekr.blaster(outdir, 100, genomes, markers, "USSpip_" + method)
        # genedict = GeneSeekr.blaster(markers, genomes, outdir, "USSpip_" + method)
        handle = open(jsonfile, 'w')
        json.dump(genedict, handle, sort_keys=True, indent=4, separators=(',', ': '))
        handle.close()
    return genedict

def alleledictbuild(TargetrMLST, nonTargetrMLST):
    typing = defaultdict(dict)
    for genome in TargetrMLST:  # genome refers to target genome
        if genome not in typing:  # add the target genome to the dictionary
            typing[genome] = defaultdict(int)

        for gene in sorted(TargetrMLST[genome]):  # gene is the rST
            for nontarget in nonTargetrMLST:  # check against this genome
                if nontarget not in typing[genome]:  # if nontarget genome not in typing dictionary then add it
                    typing[genome][nontarget] = 0
                if gene in TargetrMLST[genome] and gene in nonTargetrMLST[nontarget]:  #
                    match = 0
                    for allele in TargetrMLST[genome][gene]:  # multiple allele types possibly present
                        if allele in nonTargetrMLST[nontarget][gene]:
                            match += 1
                    if match == len(nonTargetrMLST[nontarget][gene]):
                        typing[genome][nontarget] += 1
    return typing

    return typing, removed

def sorter(genomes, outdir, target, evalue, estop, mash_cutoff):
    '''Strip first allele off each locus to feed into geneseekr and return dictionary
    '''
    # if not os.path.exists(outdir + "Genomes/"):
    #     retriever(genomes, outdir)
    if not os.path.exists(outdir):
        os.makedirs(outdir)
    if not os.path.exists(outdir + "tmp/"):
        os.makedirs(outdir + "tmp/")
    # genomes = outdir + "Genomes/"
    # nontargets = glob(genomes + "*.fa*")
    run_mash(genomes, 12)
    nontargets = read_mash("tmp/distances.txt", mash_cutoff)
    shutil.rmtree("tmp/")
    # jsonfile = '%sgenedict.json' % outdir
    # nonTargetrMLST = jsonUpGoer(jsonfile, markers, genomes, outdir, 'nontarget')
    # if os.path.exists(target):  # Determine if target is a folder
    #    targetjson = '%stargetdict.json' % outdir
    #else:
    #    print "The variable \"--targets\" is not a folder or file "
    #    return
    # TargetrMLST = jsonUpGoer(targetjson, markers, target, outdir, 'target')
    # typing, removed = compareType(TargetrMLST, nonTargetrMLST)
    # json.dump(typing, open(outdir + 'typing.json', 'w'), sort_keys=False, indent=4, separators=(',', ': '))
    # json.dump(removed, open(outdir + 'removed.json', 'w'), sort_keys=False, indent=4, separators=(',', ': '))
    # for sigtarget in typing:
    #    print typing
    #    print typing[sigtarget]
    #    SigSeekr(typing, typing[sigtarget], outdir, evalue, float(estop), 200, 1)
    if os.path.isdir(target):
        fasta_files = glob.glob(target + '/*.f*a')
        for fasta in fasta_files:
            SigSeekr(fasta, nontargets, outdir, float(evalue), float(estop), 200, 1)
    else:
        SigSeekr(target, nontargets, outdir, float(evalue), float(estop), 200, 1)


#Parser for arguments
parser = ArgumentParser(description='Find Universal Strain-Specifc Probes')
parser.add_argument('--version', action='version', version='%(prog)s v0.5')
parser.add_argument('-o', '--output', required=True, help='Specify output directory')
parser.add_argument('-i', '--input', required=True, help='Specify input genome fasta folder')
parser.add_argument('-t', '--target', required=True, help='Specify target genome or folder')
parser.add_argument('-e', '--evalue', type=float, default=1e-40, help='Specify elimination E-value lower limit (default 1e-50)')
parser.add_argument('-s', '--estop', type=float, default=1e-90, help='Specify the upper E-value limit (default 1e-90)')
parser.add_argument('-c', '--mash_cutoff', type=float, default=0.0002, help='Cutoff value to use for genome'
                                                                            ' elimination. Must be a float between'
                                                                            '0 and 1. Default is 0.0002, higher values'
                                                                            'eliminate more genomes.')
# parser.add_argument('-t', '--target', required=True, help='Specify target genome or folder')
args = vars(parser.parse_args())

sorter(
       os.path.join(os.path.abspath(args['input']), ""),
       os.path.join(os.path.abspath(args['output']), ""),
       os.path.abspath(args['target']), args['evalue'],
       args['estop'], args['mash_cutoff'])