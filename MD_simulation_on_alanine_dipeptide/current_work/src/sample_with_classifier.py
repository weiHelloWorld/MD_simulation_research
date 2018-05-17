from ANN_simulation import *

class classification_sampler(object):
    def __init__(self, index, all_states, end_state_index):    # end_states defined by pdb files
        self._index = index
        self._end_state_index = end_state_index
        self._all_states = all_states
        self._classifier = None
        self._scaling_factor = 5.0
        self._atom_selection = 'not name H*'
        return

    def get_input_from_pdbs(self, pdb_list):
        """can be modified to other input features later"""
        return Sutils.get_non_repeated_pairwise_distance(
            [pdb_list], atom_selection=self._atom_selection) / self._scaling_factor

    def get_training_data(self):
        train_in = []
        class_labels = []
        for _1, item in enumerate(self._all_states):
            temp_train_in = self.get_input_from_pdbs([item])
            temp_class_labels = np.zeros((temp_train_in.shape[0], len(self._all_states)))
            temp_class_labels[:, _1] = 1
            train_in.append(temp_train_in)
            class_labels.append(temp_class_labels)

        assert (len(train_in) == len(self._all_states))
        train_in = np.concatenate(train_in, axis=0)
        class_labels = np.concatenate(class_labels, axis=0)
        return train_in, class_labels

    def train_classifier(self):
        train_in, train_out = self.get_training_data()
        node_num = [train_in.shape[1], 100, 3]
        inputs_net = Input(shape=(node_num[0],))
        x = Dense(node_num[1], activation='tanh')(inputs_net)
        x = Dense(node_num[2], activation='softmax')(x)
        molecule_net = Model(inputs=inputs_net, outputs=x)
        molecule_net.compile(loss='categorical_crossentropy', metrics=['categorical_crossentropy'],
                             optimizer=SGD(lr=.01, momentum=.9, nesterov=True))
        call_back_list = []
        earlyStopping = EarlyStopping(monitor='val_loss', patience=30, verbose=0, mode='min')
        call_back_list += [earlyStopping]

        train_history = molecule_net.fit(train_in, train_out, epochs=200, batch_size=50,
                                         verbose=0, validation_split=0.2, callbacks=call_back_list)
        fig, axes = plt.subplots(1, 2)
        axes[0].plot(train_history.history['loss'])
        axes[1].plot(train_history.history['val_loss'])
        png_file = 'history.png'
        Helper_func.backup_rename_file_if_exists(png_file)
        fig.savefig(png_file)
        model_file = 'classifier_%02d.hdf5' % self._index
        Helper_func.backup_rename_file_if_exists(model_file)
        molecule_net.save(model_file)
        self._classifier = model_file
        return

    def get_plumed_script(self):
        molecule_net = load_model(self._classifier)
        node_num = [molecule_net.layers[0].output_shape[1], molecule_net.layers[1].output_shape[1],
                    molecule_net.layers[2].output_shape[1]]
        script = Sutils._get_plumed_script_with_pairwise_dis_as_input(
            get_index_list_with_selection_statement('../resources/alanine_dipeptide.pdb', self._atom_selection),
            self._scaling_factor)
        connection_between_layers_coeffs = [item.get_weights()[0].T.flatten() for item in
                                            molecule_net.layers if isinstance(item, Dense)]
        connection_with_bias_layers_coeffs = [item.get_weights()[1] for item in molecule_net.layers if
                                              isinstance(item, Dense)]
        index_CV_layer = 2
        temp_AE = autoencoder_Keras(1, None, None)
        script += temp_AE.get_expression_script_for_plumed(
            node_num=node_num,
            connection_between_layers_coeffs=connection_between_layers_coeffs,
            connection_with_bias_layers_coeffs=connection_with_bias_layers_coeffs,
            index_CV_layer=index_CV_layer, activation_function_list=['tanh', 'softmax'])
        script += 'mypotential: RESTRAINT ARG='
        for item in range(node_num[2]): script += 'l_2_out_%d,' % item
        return script[:-1] + ' '

    def choose_two_states_between_which_we_sample_intermediates(self):
        """is it good to alternatively choose state closest to either A or B??
        what would be a good distance metric?
        """
        input_list = [self.get_input_from_pdbs([item]) for item in self._all_states]

        return

    def sample_intermediate_between_two_states(self, state_index_1, state_index_2, folder):
        pc_string = ['0'] * len(self._all_states)
        pc_string[state_index_1] = pc_string[state_index_2] = '0.5'
        pc_string = ','.join(pc_string)
        kappa_string = ','.join(['500'] * len(self._all_states))
        out_pdb = folder + '/out_%02d_between_%02d_%02d.pdb' % (len(self._all_states), state_index_1, state_index_2)
        command = 'python ../src/biased_simulation.py 500 50000 0 %s none pc_0 --platform CPU ' % folder
        command += '--output_pdb  %s ' % out_pdb
        command += '--bias_method plumed_other --plumed_file temp_plumed.txt '
        command += ' --plumed_add_string " AT=%s KAPPA=%s"' % (pc_string, kappa_string)
        print command
        subprocess.check_output(command, shell=True)
        self._all_states.append(out_pdb)
        return
