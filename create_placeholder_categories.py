import argparse
import json
import math
import os
import random
import shutil

import utils as u
import numpy as np


def create_placeholder_categories(flavor_file, molecule_xyz_file, num_molecules, output_temp_dir):
    """
    This function creates placeholder categories that will be used by the next function to create the actual categories.
    :param flavor_file: Stores two lists: all functionals and basis sets. Example file: example_files/func_and_base.json
    :param molecule_xyz_file: Filtered dataset to sample molecules from. Example file: example_files/inputs.xyz
    :param num_molecules: The number of molecules per category
    :param output_temp_dir: The directory that stores the temporary placeholder categories
    """
    if os.path.exists(output_temp_dir):
        shutil.rmtree(output_temp_dir)

    temp_task_dir = os.path.join(output_temp_dir, "tasks")
    os.makedirs(temp_task_dir)

    with open(flavor_file, 'r') as fp:
        func_and_basis = json.load(fp)

    functionals = func_and_basis["functionals"]
    basissets = func_and_basis["basissets"]

    dft_flavors = []
    for f in functionals:
        for b in basissets:
            t = {
                "number": None,
                "set": None,  # train or test
                "functional": f,
                "basisset": b,
                "num_molecules": num_molecules
            }
            dft_flavors.append(t)

    # set number for all tasks/categories/flavors
    for i, flavor in enumerate(dft_flavors):
        flavor["number"] = str(i + 1)

    num_flavors = len(dft_flavors)

    num_digits_needed = math.ceil(np.log10(num_flavors))
    for single_flavor in dft_flavors:
        # sample X molecules
        coords_all, elements_all = u.readXYZs(molecule_xyz_file)
        assert len(coords_all) == len(elements_all)
        num_all_mol = len(coords_all)
        sampled_indices = random.sample(range(num_all_mol), int(single_flavor["num_molecules"]))
        coords = [coords_all[i] for i in sampled_indices]
        elements = [elements_all[i] for i in sampled_indices]

        task_coord_filename = f"data_01_{single_flavor['functional']}###{single_flavor['basisset']}.xyz"
        task_dir_path = os.path.join(temp_task_dir,
                                     f"T_{str(single_flavor['number']).zfill(num_digits_needed)}_"
                                     f"{single_flavor['functional']}###{single_flavor['basisset']}")

        os.mkdir(task_dir_path)

        u.exportXYZs(coords, elements, os.path.join(task_dir_path, task_coord_filename))

        with open(os.path.join(task_dir_path, "info.json"), 'w') as fp:
            json.dump(single_flavor, fp)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('flavor_file')
    parser.add_argument('molecule_xyz_file')
    parser.add_argument('num_molecules')
    parser.add_argument('output_temp_dir')
    args = parser.parse_args()
    print("Creating placeholder categories ... ")
    create_placeholder_categories(args.flavor_file, args.molecule_xyz_file, int(args.num_molecules),
                                  args.output_temp_dir)
    print("Done")