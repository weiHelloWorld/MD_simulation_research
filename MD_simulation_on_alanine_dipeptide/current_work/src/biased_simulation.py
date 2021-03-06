"""
This file is for biased simulation for alanine dipeptide only, it is used as the test for
more general file biased_simulation_general.py, which could be easily extend to other new
systems.
"""

from ANN_simulation import *
from simtk.openmm.app import *
from simtk.openmm import *
from simtk.unit import *
from sys import stdout
import ast, argparse

import os
import datetime

from config import *

parser = argparse.ArgumentParser()
parser.add_argument("record_interval", type=int, help="interval to take snapshots")
parser.add_argument("total_num_of_steps", type=int, help="total number of simulation steps")
parser.add_argument("force_constant", type=float, help="force constants")
parser.add_argument("folder_to_store_output_files", type=str, help="folder to store the output pdb and report files")
parser.add_argument("autoencoder_info_file", type=str, help="file to store autoencoder information (coefficients)")
parser.add_argument("pc_potential_center", type=str, help="potential center (should include 'pc_' as prefix)")
parser.add_argument("--out_traj", type=str, default=None, help="output trajectory file")
parser.add_argument("--layer_types", type=str, default=str(CONFIG_27), help='layer types')
parser.add_argument("--num_of_nodes", type=str, default=str(CONFIG_3[:3]), help='number of nodes in each layer')
parser.add_argument("--temperature", type=int, default= CONFIG_21, help='simulation temperature')
parser.add_argument("--data_type_in_input_layer", type=int, default=1, help='data_type_in_input_layer, 0 = cos/sin, 1 = Cartesian coordinates')
parser.add_argument("--platform", type=str, default=CONFIG_23, help='platform on which the simulation is run')
parser.add_argument("--scaling_factor", type=float, default = float(CONFIG_49), help='scaling_factor for ANN_Force')
parser.add_argument("--starting_pdb_file", type=str, default='../resources/alanine_dipeptide.pdb', help='the input pdb file to start simulation')
parser.add_argument("--starting_frame", type=int, default=0, help="index of starting frame in the starting pdb file")
parser.add_argument("--minimize_energy", type=int, default=1, help='whether to minimize energy (1 = yes, 0 = no)')
parser.add_argument("--equilibration_steps", type=int, default=1000, help="number of steps for the equilibration process")
# next few options are for metadynamics
parser.add_argument("--bias_method", type=str, default='US', help="biasing method for enhanced sampling, US = umbrella sampling, MTD = metadynamics")
parser.add_argument("--MTD_pace", type=int, default=CONFIG_66, help="pace of metadynamics")
parser.add_argument("--MTD_height", type=float, default=CONFIG_67, help="height of metadynamics")
parser.add_argument("--MTD_sigma", type=float, default=CONFIG_68, help="sigma of metadynamics")
parser.add_argument("--MTD_WT", type=int, default=CONFIG_69, help="whether to use well-tempered version")
parser.add_argument("--MTD_biasfactor", type=float, default=CONFIG_70, help="biasfactor of well-tempered metadynamics")
# following is for plumed script
parser.add_argument("--plumed_file", type=str, default=None, help="plumed script for biasing force, used only when the bias_method == plumed_other")
parser.add_argument("--plumed_add_string", type=str, default="", help="additional string to be attached to the end of plumed script in args.plumed_file")
# note on "force_constant_adjustable" mode:
# the simulation will stop if either:
# force constant is greater or equal to max_force_constant
# or distance between center of data cloud and potential center is smaller than distance_tolerance
parser.add_argument("--fc_adjustable", help="set the force constant to be adjustable", action="store_true")
parser.add_argument("--max_fc", type=float, default=CONFIG_32, help="max force constant (for force_constant_adjustable mode)")
parser.add_argument("--fc_step", type=float, default=CONFIG_34, help="the value by which the force constant is increased each time (for force_constant_adjustable mode)")
parser.add_argument("--distance_tolerance", type=float, default=CONFIG_35, help="max distance allowed between center of data cloud and potential center (for force_constant_adjustable mode)")
parser.add_argument("--autoencoder_file", type=str, help="pkl file that stores autoencoder (for force_constant_adjustable mode)")
parser.add_argument("--remove_previous", help="remove previous outputs while adjusting force constants", action="store_true")
args = parser.parse_args()

record_interval = args.record_interval
total_number_of_steps = args.total_num_of_steps
input_data_type = ['cossin', 'Cartesian', 'pairwise'][args.data_type_in_input_layer]
force_constant = args.force_constant
scaling_factor = args.scaling_factor
layer_types = re.sub("\[|\]|\"|\'| ",'', args.layer_types).split(',')
num_of_nodes = re.sub("\[|\]|\"|\'| ",'', args.num_of_nodes).split(',')
num_of_nodes = [int(item) for item in num_of_nodes]
out_format = '.dcd' if args.out_traj is None else os.path.splitext(args.out_traj)[1]

if float(force_constant) != 0:
    from ANN import *

folder_to_store_output_files = args.folder_to_store_output_files # this is used to separate outputs for different networks into different folders
autoencoder_info_file = args.autoencoder_info_file

potential_center = list([float(x) for x in args.pc_potential_center.replace('"','')\
                                .replace('pc_','').split(',')])   # this API is the generalization for higher-dimensional cases

if not os.path.exists(folder_to_store_output_files):
    try: os.makedirs(folder_to_store_output_files)
    except: pass

def run_simulation(force_constant):
    assert(os.path.exists(folder_to_store_output_files))
    input_pdb_file_of_molecule = args.starting_pdb_file
    force_field_file = 'amber99sb.xml'
    water_field_file = 'tip3p.xml'
    pdb_reporter_file = '%s/output_fc_%f_pc_%s.pdb' %(folder_to_store_output_files, force_constant, str(potential_center).replace(' ',''))

    if not args.out_traj is None:
        pdb_reporter_file = args.out_traj

    state_data_reporter_file = pdb_reporter_file.replace('output_fc', 'report_fc').replace('.pdb', '.txt')

    # check if the file exist
    for item_filename in [pdb_reporter_file, state_data_reporter_file]:
        Helper_func.backup_rename_file_if_exists(item_filename)

    index_of_backbone_atoms = CONFIG_57[0]
    flag_random_seed = 0 # whether we need to fix this random seed

    simulation_temperature = args.temperature
    time_step = CONFIG_22   # simulation time step, in ps

    pdb = PDBFile(input_pdb_file_of_molecule)
    modeller = Modeller(pdb.topology, pdb.getPositions(frame=args.starting_frame))
    solvent_opt = 'no_water'
    if solvent_opt == 'explicit':
        forcefield = ForceField(force_field_file, water_field_file)
        modeller.addSolvent(forcefield, model=water_field_file.split('.xml')[0], boxSize=Vec3(3, 3, 3) * nanometers,
                            ionicStrength=0 * molar)
        system = forcefield.createSystem(modeller.topology, nonbondedMethod=PME, nonbondedCutoff=1.0 * nanometers,
                                         constraints=AllBonds, ewaldErrorTolerance=0.0005)
    else:
        forcefield = ForceField(force_field_file)
        system = forcefield.createSystem(modeller.topology, nonbondedMethod=NoCutoff, constraints=AllBonds)

    if args.bias_method == "US":
        if float(force_constant) != 0:
            force = ANN_Force()
            force.set_layer_types(layer_types)
            force.set_data_type_in_input_layer(args.data_type_in_input_layer)
            force.set_list_of_index_of_atoms_forming_dihedrals_from_index_of_backbone_atoms(index_of_backbone_atoms)
            force.set_index_of_backbone_atoms(index_of_backbone_atoms)
            if args.data_type_in_input_layer == 2:
                force.set_list_of_pair_index_for_distances(CONFIG_80)

            force.set_num_of_nodes(num_of_nodes)
            force.set_potential_center(potential_center)
            force.set_force_constant(float(force_constant))
            unit_scaling = 1.0  # TODO: check unit scaling
            force.set_scaling_factor(float(scaling_factor) / unit_scaling)   # since default unit is nm in OpenMM

            # TODO: need to fix following for multi-hidden layer cases
            temp_coeffs, temp_bias = np.load(autoencoder_info_file)
            for item_layer_index in [0, 1]:
                assert (len(temp_coeffs[item_layer_index]) ==
                        num_of_nodes[item_layer_index] * num_of_nodes[item_layer_index + 1]), (len(temp_coeffs[item_layer_index]),
                                (num_of_nodes[item_layer_index], num_of_nodes[item_layer_index + 1]))
                assert (len(temp_bias[item_layer_index]) == num_of_nodes[item_layer_index + 1]), (len(temp_bias[item_layer_index]), num_of_nodes[item_layer_index + 1])

            # need tolist() since C++ only accepts Python list
            force.set_coeffients_of_connections([item_w.tolist() for item_w in temp_coeffs])
            force.set_values_of_biased_nodes([item_w.tolist() for item_w in temp_bias])

            system.addForce(force)
    elif args.bias_method == "US_on_phipsi":
        from openmmplumed import PlumedForce
        kappa_string = ','.join([str(force_constant) for _ in potential_center])
        plumed_force_string = """
phi: TORSION ATOMS=5,7,9,15
psi: TORSION ATOMS=7,9,15,17
restraint: RESTRAINT ARG=phi,psi AT=%f,%f KAPPA=%s
PRINT STRIDE=10 ARG=* FILE=COLVAR
        """ % (potential_center[0], potential_center[1], kappa_string)
        system.addForce(PlumedForce(plumed_force_string))
    elif args.bias_method == "MTD":
        from openmmplumed import PlumedForce
        plumed_force_string = Alanine_dipeptide.get_expression_script_for_plumed()
        with open(autoencoder_info_file, 'r') as f_in:
            plumed_force_string += f_in.read()

        # note that dimensionality of MTD is determined by potential_center string
        plumed_script_ANN_mode = 'ANN'
        if plumed_script_ANN_mode == 'native':
            mtd_output_layer_string = ['l_2_out_%d' % item for item in range(len(potential_center))]
        elif plumed_script_ANN_mode == 'ANN':
            mtd_output_layer_string = ['ann_force.%d' % item for item in range(len(potential_center))]
        else: raise Exception('mode error')

        mtd_output_layer_string = ','.join(mtd_output_layer_string)
        mtd_sigma_string = ','.join([str(args.MTD_sigma) for _ in range(len(potential_center))])
        if args.MTD_WT:
            mtd_well_tempered_string = 'TEMP=%d BIASFACTOR=%f' % (args.temperature, args.MTD_biasfactor)
        else:
            mtd_well_tempered_string = ""
        plumed_force_string += """
metad: METAD ARG=%s PACE=%d HEIGHT=%f SIGMA=%s FILE=temp_MTD_hills.txt %s
PRINT STRIDE=%d ARG=%s,metad.bias FILE=temp_MTD_out.txt
""" % (mtd_output_layer_string, args.MTD_pace, args.MTD_height, mtd_sigma_string, mtd_well_tempered_string,
       record_interval, mtd_output_layer_string)
        # print plumed_force_string
        system.addForce(PlumedForce(plumed_force_string))
    elif args.bias_method == "SMD":
        # TODO: this is temporary version
        from openmmplumed import PlumedForce
        kappa_string = '1000,1000'
        plumed_force_string = """
phi: TORSION ATOMS=5,7,9,15
psi: TORSION ATOMS=7,9,15,17
restraint: MOVINGRESTRAINT ARG=phi,psi AT0=-1.5,1.0  STEP0=0 KAPPA0=%s AT1=1.0,-1.0 STEP1=%d KAPPA1=%s
PRINT STRIDE=10 ARG=* FILE=COLVAR
""" % (kappa_string, total_number_of_steps, kappa_string)
        system.addForce(PlumedForce(plumed_force_string))
    elif args.bias_method == "TMD":  # targeted MD
        # TODO: this is temporary version
        from openmmplumed import PlumedForce
        kappa_string = '10000'
        plumed_force_string = """
phi: TORSION ATOMS=5,7,9,15
psi: TORSION ATOMS=7,9,15,17
rmsd: RMSD REFERENCE=../resources/alanine_ref_1_TMD.pdb TYPE=OPTIMAL
restraint: MOVINGRESTRAINT ARG=rmsd AT0=0 STEP0=0 KAPPA0=0 AT1=0 STEP1=%d KAPPA1=%s
PRINT STRIDE=10 ARG=* FILE=COLVAR
        """ % (total_number_of_steps, kappa_string)
        system.addForce(PlumedForce(plumed_force_string))
    elif args.bias_method == "plumed_other":
        from openmmplumed import PlumedForce
        with open(args.plumed_file, 'r') as f_in:
            plumed_force_string = f_in.read().strip() + args.plumed_add_string
        system.addForce(PlumedForce(plumed_force_string))
    else:
        raise Exception('bias method error')
    # end of biased force

    integrator = LangevinIntegrator(simulation_temperature*kelvin, 1/picosecond, time_step*picoseconds)
    if flag_random_seed:
        integrator.setRandomNumberSeed(1)  # set random seed

    platform = Platform.getPlatformByName(args.platform)
    platform.loadPluginsFromDirectory(CONFIG_25)  # load the plugin from specific directory

    simulation = Simulation(modeller.topology, system, integrator, platform)
    simulation.context.setPositions(modeller.positions)
    if args.minimize_energy:
        print('begin Minimizing energy...')
        print(datetime.datetime.now())
        simulation.minimizeEnergy()
        print('Done minimizing energy.')
        print(datetime.datetime.now())
    else:
        print('energy minimization not required')

    simulation.step(args.equilibration_steps)
    if out_format == '.pdb':
        simulation.reporters.append(PDBReporter(pdb_reporter_file, record_interval))
    elif out_format == '.dcd':
        simulation.reporters.append(DCDReporter(pdb_reporter_file.replace('.pdb', '.dcd'), record_interval))
    simulation.reporters.append(StateDataReporter(state_data_reporter_file, record_interval,
                                    step=True, potentialEnergy=True, kineticEnergy=True, speed=True,
                                                  temperature=True, progress=True, remainingTime=True,
                                                  totalSteps=total_number_of_steps + args.equilibration_steps,
                                                  ))
    simulation.step(total_number_of_steps)

    print('Done biased simulation!')
    return pdb_reporter_file

def get_distance_between_data_cloud_center_and_potential_center(pdb_file):
    coor_file = Alanine_dipeptide().generate_coordinates_from_pdb_files(pdb_file)[0]
    temp_network = autoencoder.load_from_pkl_file(args.autoencoder_file)
    this_simulation_data = single_biased_simulation_data(temp_network, coor_file)
    offset = this_simulation_data.get_offset_between_potential_center_and_data_cloud_center(input_data_type)
    if layer_types[1] == "Circular":
        offset = [min(abs(item), abs(item + 2 * np.pi), abs(item - 2 * np.pi)) for item in offset]
        print("circular offset")
    print('offset = %s' % str(offset))
    distance = sqrt(sum([item * item for item in offset]))
    return distance


def run_simulation_ssages(force_constant):
    ssages_output_file = '%s/output_fc_%f_pc_%s.json' % (
        folder_to_store_output_files, force_constant, str(potential_center).replace(' ', ''))
    subprocess.check_output('python ../src/temp_create_json_ssages.py %s %s %s %s %s' % (
        ssages_output_file, str(potential_center).replace(' ', ''), autoencoder_info_file.replace('.npy', '.txt'),
        ssages_output_file.replace('.json', '.trr'), force_constant), shell=True)
    command = "ssages " + ssages_output_file
    subprocess.check_output(command, shell=True)
    pdb_reporter_file = ssages_output_file.replace('.json', '.pdb')
    subprocess.check_output('mdconvert -o %s %s -t ../resources/alanine_dipeptide.pdb' % (
        pdb_reporter_file, pdb_reporter_file.replace('.pdb', '.trr')), shell = True)
    return pdb_reporter_file


if __name__ == '__main__':
    if not args.fc_adjustable:
        run_simulation(args.force_constant)
    else:
        force_constant = args.force_constant
        distance_of_data_cloud_center = float("inf")
        while force_constant < args.max_fc and distance_of_data_cloud_center > args.distance_tolerance:
            if args.remove_previous:
                try:
                    command = 'rm %s/*%s*' % (folder_to_store_output_files, str(potential_center).replace(' ',''))
                    command = command.replace('[','').replace(']','')
                    subprocess.check_output(command, shell=True)
                    print("removing previous results...")
                except:
                    pass
            pdb_file = run_simulation(force_constant)
            distance_of_data_cloud_center = get_distance_between_data_cloud_center_and_potential_center(pdb_file)
            force_constant += args.fc_step
            print("distance_between_data_cloud_center_and_potential_center = %f" % distance_of_data_cloud_center)

