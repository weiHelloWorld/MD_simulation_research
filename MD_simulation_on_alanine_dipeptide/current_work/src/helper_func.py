from config import *
from scipy.special import erf

class Helper_func(object):
    def __init__(self):
        return

    @staticmethod
    def get_mutual_info_of_two_continuous_vars(temp_var_0, temp_var_1, bins=10, normalization=True):
        temp_hist_0, _ = np.histogramdd(temp_var_0, bins=bins)
        temp_hist_1, _ = np.histogramdd(temp_var_1, bins=bins)
        temp_hist_2, _ = np.histogramdd(np.array([temp_var_0, temp_var_1]).T, bins=bins)
        temp_hist_0 /= temp_hist_0.sum()
        temp_hist_1 /= temp_hist_1.sum()
        temp_hist_2 /= temp_hist_2.sum()
        result = np.sum([temp_hist_2[item_x, item_y] * np.log(
            temp_hist_2[item_x, item_y] / temp_hist_0[item_x] / temp_hist_1[item_y])
                     for item_x in range(bins) for item_y in range(bins) if temp_hist_2[item_x, item_y] != 0])
        if normalization:
            entropy_0 = - np.sum(temp_hist_0 * np.log(temp_hist_0))
            entropy_1 = - np.sum(temp_hist_1 * np.log(temp_hist_1))
            result /= (0.5 * (entropy_0 + entropy_1))
        return result

    @staticmethod
    def generate_alkane_residue_code_in_openmm_xml(num, name):
        print '''<Residue name="%s">
<Atom charge="0.09" name="H11" type="HGA3"/>
<Atom charge="0.09" name="H12" type="HGA3"/>
<Atom charge="0.09" name="H13" type="HGA3"/>
<Atom charge="-0.27" name="C1" type="CG331"/>''' % name
        for item in range(num - 2):
            print '''<Atom charge="0.09" name="H%d1" type="HGA2"/>
<Atom charge="0.09" name="H%d2" type="HGA2"/>
<Atom charge="-0.18" name="C%d" type="CG321"/>''' % (item + 2, item + 2, item + 2)
        print """<Atom charge="0.09" name="H%d1" type="HGA3"/>
<Atom charge="0.09" name="H%d2" type="HGA3"/>
<Atom charge="0.09" name="H%d3" type="HGA3"/>
<Atom charge="-0.27" name="C%d" type="CG331"/>
<Bond atomName1="H11" atomName2="C1"/>
<Bond atomName1="H12" atomName2="C1"/>
<Bond atomName1="H13" atomName2="C1"/>""" % (num, num, num, num)
        for item in range(num - 1):
            print """<Bond atomName1="C%d" atomName2="C%d"/>
<Bond atomName1="H%d1" atomName2="C%d"/>
<Bond atomName1="H%d2" atomName2="C%d"/>""" % (item + 1, item + 2, item + 2, item + 2, item + 2, item + 2)
        print """<Bond atomName1="H%d3" atomName2="C%d"/>
<AllowPatch name="MET1"/>
<AllowPatch name="MET2"/>
</Residue>""" % (num, num)
        return

    @staticmethod
    def check_center_of_mass_is_at_origin(result):
        coords_of_center_of_mass_after = [[np.average(result[item, ::3]), np.average(result[item, 1::3]),
                                           np.average(result[item, 2::3])]
                                          for item in range(result.shape[0])]
        return np.all(np.abs(np.array(coords_of_center_of_mass_after).flatten()) < 1e-5)

    @staticmethod
    def remove_translation(coords):  # remove the translational degree of freedom
        if len(coords.shape) == 1:  # convert 1D array (when there is only one coord) to 2D array
            coords = coords.reshape((1, coords.shape[0]))
        number_of_atoms = coords.shape[1] / 3
        coords_of_center_of_mass = [[np.average(coords[item, ::3]), np.average(coords[item, 1::3]),
                                     np.average(coords[item, 2::3])] * number_of_atoms
                                    for item in range(coords.shape[0])]
        result = coords - np.array(coords_of_center_of_mass)
        assert Helper_func.check_center_of_mass_is_at_origin(result)
        return result

    @staticmethod
    def get_gyration_tensor_and_principal_moments(coords):
        coords = Helper_func.remove_translation(coords)
        temp_coords = coords.reshape(coords.shape[0], coords.shape[1] / 3, 3)
        gyration = np.zeros((coords.shape[0], 3, 3))
        for xx in range(3):
            for yy in range(3):
                gyration[:, xx, yy] = (temp_coords[:, :, xx] * temp_coords[:, :, yy]).mean(axis=-1)
        moments_gyration = np.linalg.eig(gyration)[0]
        moments_gyration.sort(axis=-1)
        return gyration, moments_gyration[:, ::-1]

    @staticmethod
    def get_norm_factor(rcut, sig):
        rcut2 = rcut*rcut
        sig2 = 2.0*sig*sig
        normconst = np.sqrt( np.pi * sig2 ) * erf( rcut / (sqrt(2.0)*sig) ) - 2*rcut* np.exp( - rcut2 / sig2 )
        preerf = np.sqrt( 0.5 * np.pi * sig * sig ) / normconst
        prelinear = np.exp( - rcut2 / sig2 ) / normconst
        return normconst, preerf, prelinear

    @staticmethod
    def get_coarse_grained_count(dis, r_hi, rcut, sig):
        # TODO: test if this function is correct
        normconst, preerf, prelinear = Helper_func.get_norm_factor(rcut, sig)
        hiMinus = r_hi - rcut
        hiPlus = r_hi + rcut
        count = np.float64((dis <= hiPlus).sum(axis=-1))
        temp_in_boundary_region = ((dis > hiMinus) & (dis <= hiPlus))
        temp_correction = ( 0.5 + preerf * erf( np.sqrt(0.5) * (dis - r_hi)/sig ) \
                                             - prelinear * (dis - r_hi))
        # print count.shape, temp_in_boundary_region.shape, temp_correction.shape
        count -= (temp_in_boundary_region * temp_correction).sum(axis=-1)
        actual_count = (dis < r_hi).sum(axis=-1)
        return count, actual_count

    @staticmethod
    def compute_distances_min_image_convention(atoms_pos_1, atoms_pos_2, box_length):
        # shape of atoms_pos_{1,2}: (num of frames, num of atoms * 3)
        # output: distance matrix
        # why don't we use mdtraj?  Because it requires large memory for loading large pdb files
        # why don't we use MDAnalysis?  Because it is not fast enough (looping over trajectory would take long time)
        # this function is especially useful when both atoms_pos_1, atoms_pos_2 are not super long, while the number of frames is large, 
        # since it vectorizes computation over frames
        temp_dis_2 = np.zeros((atoms_pos_1.shape[0], atoms_pos_1.shape[1] / 3, atoms_pos_2.shape[1] / 3))
        for index_1 in range(atoms_pos_1.shape[1] / 3):
            # print index_1
            for index_2 in range(atoms_pos_2.shape[1] / 3):
                temp_diff = atoms_pos_1[:, 3 * index_1: 3 * index_1 + 3] - atoms_pos_2[:, 3 * index_2: 3 * index_2 + 3]
                temp_vec = np.array([(item + box_length / 2.0) % box_length - box_length / 2.0 for item in temp_diff.T])
                temp_dis_2[:, index_1, index_2] = np.linalg.norm(temp_vec, axis=0)
        return temp_dis_2

    @staticmethod
    def get_index_list_of_O_atom_in_water(pdb_file, ignore_TER_line):
        """this is used for solvent analysis, e.g. biased simulation with PLUMED"""
        temp_u = Universe(pdb_file)
        atom_sel = temp_u.select_atoms('resname HOH and name O')
        if ignore_TER_line: return atom_sel.indices + 1
        else: raise Exception('double check your pdb')

    @staticmethod
    def get_list_of_cg_count_for_atom_list(pdb_file, atom_selection, box_length, r_hi, rcut, sig):
        """ cg = coarse grained, atom list is specified by atom_selection """
        temp_u = Universe(pdb_file)
        water_pos, atoms_pos = [], []
        water_sel = temp_u.select_atoms('resname HOH and name O')
        atoms_sel = temp_u.select_atoms(atom_selection)
        for _ in temp_u.trajectory:
            water_pos.append(water_sel.positions.flatten())
            atoms_pos.append(atoms_sel.positions.flatten())
        atoms_pos = np.array(atoms_pos)
        water_pos = np.array(water_pos)
        distances = Helper_func.compute_distances_min_image_convention(atoms_pos_1=atoms_pos, atoms_pos_2=water_pos, box_length=box_length)
        return Helper_func.get_coarse_grained_count(distances, r_hi, rcut, sig)

    @staticmethod
    def get_plumed_script_for_biased_simulation_with_INDUS_cg_input_and_ANN(
            water_index_string, atom_indices, r_high, scaling_factor, ANN_plumed_string,
            potential_center, force_constant, out_plumed_file='temp_ndata.txt'):
        """ used to generate plumed script for biased simulation, with INDUS coarse grained water
        molecule numbers as input for ANN, and biasing force is applied on outputs of ANN
        """
        result = ''
        for _1, item in enumerate(atom_indices):
            result += "sph_%d: SPHSHMOD ATOMS=%s ATOMREF=%d RLOW=-0.5 RHIGH=%f SIGMA=0.01 CUTOFF=0.02\n" % (
                            _1, water_index_string, item, r_high)
            result += "l_0_out_%d: COMBINE PERIODIC=NO COEFFICIENTS=%f ARG=sph_%d.Ntw\n" % (_1, 1.0 / scaling_factor, _1)
        result += ANN_plumed_string    # add string generated by ANN plumed plugin
        arg_string = ','.join(['ann_force.%d' % _2 for _2 in range(len(potential_center))])
        pc_string = ','.join([str(_2) for _2 in potential_center])
        kappa_string = ','.join([str(force_constant) for _ in potential_center])
        arg_string_2 = ','.join(['l_0_out_%d' % _2 for _2 in range(len(atom_indices))])
        result += """\nmypotential: RESTRAINT ARG=%s AT=%s KAPPA=%s
ave: COMBINE PERIODIC=NO ARG=%s

PRINT STRIDE=50 ARG=%s,ave FILE=%s""" % (
            arg_string, pc_string, kappa_string, arg_string_2, arg_string, out_plumed_file
        )
        return result

    @staticmethod
    def get_radial_distribution(distances, num, nbins, dr, length):
        hist = np.zeros(nbins, )
        for item in distances:
            temp_target_index = int(item / dr)
            if temp_target_index < nbins:
                hist[temp_target_index] += 1.0 / (4 / 3.0 * np.pi) / (
                            ((temp_target_index + 1) * dr) ** 3 - ((temp_target_index + 0) * dr) ** 3)
        return hist / (num / length ** 3)

    @staticmethod
    def backup_rename_file_if_exists(filename):
        extension = '.' + filename.split('.')[-1]
        if os.path.isfile(filename):  # backup file if previous one exists
            new_filename = filename + ".bak_" + datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S") + extension
            os.rename(filename, new_filename)
        else: new_filename = None
        return new_filename