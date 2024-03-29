from __future__ import print_function
from __future__ import absolute_import
import uuid
import os
import numpy as np
import subprocess
import shlex
import yaml

import utils.xyz_utils as xyz

kcal_to_eV=0.0433641153
kB=8.6173303e-5 #eV/K
T=298.15
kBT=kB*T
AToBohr=1.889725989
HToeV = 27.211399

def do_xtb_runs(settings, name, coords_todo, elements_todo):
    if "test" in name:
        outdir = settings["outdir_test"]
    else:
        outdir = settings["outdir"]
    # initial xtb runs
    if os.path.exists("%s/es_%s.txt"%(outdir, name)) and not settings["overwrite"]:
        print("   ---   load %s labels"%(name))
        es = np.loadtxt("%s/es_%s.txt"%(outdir, name))
    else:
        print("   ---   load t%s labels"%(name))
        es = run_xtb(coords_todo, elements_todo)
        np.savetxt("%s/es_train.txt"%(outdir, name), es)
    return(es)


def run_xtb(coords, elements):
    es = []
    for molidx in range(len(coords)):
        c_here = coords[molidx]
        el_here = elements[molidx]
        results = xtb_calc(c_here, el_here, opt=False, grad=False, hess=False, charge=0, freeze=[])
        e = results["energy"]
        es.append(e)
    es = np.array(es)
    return(es)


def get_hess(settings):
    outdir = settings["outdir"]
    if os.path.exists("%s/results_start.yml"%(outdir)) and not settings["overwrite"]:
        print("   ---   load optimized molecule and hessian")
        infile=open("%s/results_start.yml"%(outdir),"r")
        results_start = yaml.load(infile, Loader=yaml.Loader)
    else:
        print("   ---   optimize molecule and calculate hessian")
        results_start = xtb_calc(settings["coords"], settings["elements"], opt=True, grad=False, hess=True, charge=0, freeze=[])
        outfilename="%s/results_start.yml"%(outdir)
        outfile=open(outfilename,"w")
        outfile.write(yaml.dump(results_start, default_flow_style=False))
        outfile.close()
    n = settings["n"]
    hess = results_start["hessian"].reshape(3*n,n,3)
    settings["hess"] = hess
    settings["vibspectrum"] = results_start["vibspectrum"]
    settings["reduced_masses"] = results_start["reduced_masses"]
    return(hess)



def xtb_calc(coords, elements, opt=False, grad=False, hess=False, charge=0, freeze=[]):

    if opt and grad:
        exit("opt and grad are exclusive")
    if hess and grad:
        exit("hess and grad are exclusive")

    if hess or grad:
        if len(freeze)!=0:
            print("WARNING: please test the combination of hess/grad and freeze carefully")

    rundir="xtb_tmpdir_%s"%(uuid.uuid4())
    if not os.path.exists(rundir):
        os.makedirs(rundir)
    else:
        if len(os.listdir(rundir))>0:
            os.system("rm %s/*"%(rundir))

    startdir=os.getcwd()
    os.chdir(rundir)

    xyz.exportXYZ(coords, elements, "in.xyz")

    if len(freeze)>0:
        outfile=open("xcontrol","w")
        outfile.write("$fix\n")
        outfile.write(" atoms: ")
        for counter,i in enumerate(freeze):
            if (counter+1)<len(freeze):
                outfile.write("%i,"%(i+1))
            else:
                outfile.write("%i\n"%(i+1))
        #outfile.write("$gbsa\n solvent=toluene\n")
        outfile.close()
        add=" -I xcontrol "
    else:
        add=""

    if charge==0:
        if opt:
            if hess:
                command = "xtb %s in.xyz --ohess"%(add)
            else:
                command = "xtb %s in.xyz --opt"%(add)
        else:
            if grad:
                command = "xtb %s in.xyz --grad"%(add)
            else:
                command = "xtb %s in.xyz"%(add)

    else:
        if opt:
            if hess:
                command = "xtb %s in.xyz --ohess --chrg %i"%(add,charge)
            else:
                command = "xtb %s in.xyz --opt --chrg %i"%(add,charge)
        else:
            if grad:
                command = "xtb %s in.xyz --grad --chrg %i"%(add,charge)
            else:
                command = "xtb %s in.xyz --chrg %i"%(add,charge)


    os.environ["OMP_NUM_THREADS"]="10" # "%s"%(settings["OMP_NUM_THREADS"])
    os.environ["MKL_NUM_THREADS"]="10" # "%s"%(settings["MKL_NUM_THREADS"])


    args = shlex.split(command)

    mystdout = open("xtb.log", "a")
    process = subprocess.Popen(args, stdout=mystdout, stderr=subprocess.PIPE)
    out, err = process.communicate()
    mystdout.close()


    if opt:
        if not os.path.exists("xtbopt.xyz"):
            print("WARNING: xtb geometry optimization did not work")
            coords_new, elements_new = None, None
        else:
            coords_new, elements_new = xyz.readXYZ("xtbopt.xyz")
    else:
        coords_new, elements_new = None, None

    if grad:
        grad = read_xtb_grad()
    else:
        grad = None

    if hess:
        hess, vibspectrum, reduced_masses = read_xtb_hess()
    else:
        hess, vibspectrum, reduced_masses = None, None, None

    e = read_xtb_energy()

    os.chdir(startdir)

    os.system("rm -r %s"%(rundir))

    results={"energy": e, "coords": coords_new, "elements": elements_new, "gradient": grad, "hessian": hess, "vibspectrum": vibspectrum, "reduced_masses": reduced_masses}
    return(results)


def read_xtb_energy():
    if not os.path.exists("xtb.log"):
        return(None)
    energy=None
    for line in open("xtb.log"):
        if "| TOTAL ENERGY" in line:
            energy = float(line.split()[3])*HToeV
    return(energy)


def read_xtb_grad():
    if not os.path.exists("gradient"):
        return(None)
    grad = []
    for line in open("gradient","r"):
        if len(line.split())==3:
            grad.append([float(line.split()[0]), float(line.split()[1]), float(line.split()[2])])
    if len(grad)==0:
        grad=None
    else:
        grad = np.array(grad)*HToeV*AToBohr
    return(grad)


def read_xtb_hess():
    hess = None
    if not os.path.exists("hessian"):
        return(None, None, None)
    hess = []
    for line in open("hessian","r"):
        if "hess" not in line:
            for x in line.split():
                hess.append(float(x))
    if len(hess)==0:
        hess=None
    else:
        hess = np.array(hess)

    vibspectrum = None
    if not os.path.exists("vibspectrum"):
        return(None, None, None)
    vibspectrum = []
    read=False
    for line in open("vibspectrum","r"):
        if "end" in line:
            read=False

        if read:
            if len(line.split())==5:
                vibspectrum.append(float(line.split()[1]))
            elif len(line.split())==6:
                vibspectrum.append(float(line.split()[2]))
            else:
                print("WARNING: weird line length: %s"%(line))
        if "RAMAN" in line:
            read=True
    
    reduced_masses = None
    if not os.path.exists("g98.out"):
        print("g98.out not found")
        return(None, None, None)
    reduced_masses = []
    read=False
    for line in open("g98.out","r"):
        if "Red. masses" in line:
            for x in line.split()[3:]:
                try:
                    reduced_masses.append(float(x))
                except:
                    pass

    if len(vibspectrum)==0:
        vibspectrum=None
        print("no vibspectrum found")
    else:
        vibspectrum = np.array(vibspectrum)

    if len(reduced_masses)==0:
        reduced_masses = None
        print("no reduced masses found")
    else:
        reduced_masses = np.array(reduced_masses)

    return(hess, vibspectrum, reduced_masses)
