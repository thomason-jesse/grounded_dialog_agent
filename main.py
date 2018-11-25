#!/usr/bin/env python
__author__ = 'jesse'

import sys
sys.path.append('../tsp/')  # necessary to import CKYParser from above directory
sys.path.append('/home/users/jthomason/catkin_ws/src/perception_classifiers/src/phm/tsp/')

import argparse
import pickle
import Agent
import KBGrounder
import IO
import os
try:
    import rospy
except ImportError:
    print("WARNING: cannot import ros-related libraries")
    rospy = None


def main():

    # Load parameters from command line.
    parser_fn = FLAGS_parser_fn
    word_embeddings_fn = FLAGS_word_embeddings_fn
    io_type = FLAGS_io_type
    grounder_fn = FLAGS_grounder_fn
    active_train_set = [int(oidx) for oidx in FLAGS_active_train_set.split(',')] if FLAGS_active_train_set is not None else None
    kb_static_facts_fn = None
    kb_perception_source_dir = None
    kb_perception_feature_dir = None
    active_test_set = None
    if grounder_fn is None:
        kb_static_facts_fn = FLAGS_kb_static_facts_fn
        kb_perception_source_dir = FLAGS_kb_perception_source_dir
        kb_perception_feature_dir = FLAGS_kb_perception_feature_dir
        active_test_set = [int(oidx) for oidx in FLAGS_active_test_set.split(',')]
    write_classifiers = FLAGS_write_classifiers
    uid = FLAGS_uid
    data_dir = FLAGS_data_dir
    client_dir = FLAGS_client_dir
    spin_time = FLAGS_spin_time
    num_dialogs = FLAGS_num_dialogs
    init_phase = FLAGS_init_phase
    max_syn_qs = FLAGS_max_syn_qs
    max_opp_qs = FLAGS_max_opp_qs
    image_path = FLAGS_image_path
    no_clarify = FLAGS_no_clarify.split(',') if FLAGS_no_clarify is not None else None
    assert io_type == 'keyboard' or io_type == 'server' or io_type == 'robot'
    assert io_type != 'server' or (uid is not None and client_dir is not None and data_dir is not None)
    assert io_type != 'robot' or image_path is not None

    if grounder_fn is None:

        # Load the parser from file.
        print("main: loading parser from file...")
        with open(parser_fn, 'rb') as f:
            p = pickle.load(f)
        p.lexicon.wv = p.lexicon.load_word_embeddings(word_embeddings_fn)
        print("main: ... done")

        # Create a new labels.pickle that erases the labels of the active training set for test purposes.
        full_annotation_fn = os.path.join(kb_perception_source_dir, 'full_annotations.pickle')
        if os.path.isfile(full_annotation_fn):
            print("main: creating new labels.pickle that blinds the active training set for this test...")
            with open(full_annotation_fn, 'rb') as f:
                fa = pickle.load(f)
            with open(os.path.join(kb_perception_source_dir, 'labels.pickle'), 'wb') as f:
                labels = []
                for oidx in fa:
                    if active_train_set is None or oidx not in active_train_set:
                        for pidx in range(len(fa[oidx])):
                            labels.append((pidx, oidx, fa[oidx][pidx]))
                pickle.dump(labels, f)
            print("main: ... done")

        # Instantiate a grounder.
        print("main: instantiating grounder...")
        g = KBGrounder.KBGrounder(p, kb_static_facts_fn, kb_perception_source_dir, kb_perception_feature_dir,
                                  active_test_set)
        if write_classifiers:
            print("main: and writing grounder perception classifiers to file...")
            g.kb.pc.commit_changes()  # save classifiers to disk
        print("main: ... done")

    else:
        # Load a grounder from file
        print("main: loading grounder from file...")
        with open(grounder_fn, 'rb') as f:
            g = pickle.load(f)
        print("main: ... done")

        # Grab a reference to the parser from the loaded grounder.
        p = g.parser

    # Instantiate an input/output
    print("main: instantiating IO...")
    use_shorter_utterances = False
    if io_type == 'keyboard':
        io = IO.KeyboardIO()
    elif io_type == 'server':
        io = IO.SeverIO(uid, client_dir, spin_time=spin_time)
    elif io_type == 'robot':  # includes some hard-coded expectations like 2 tables, 8 training objects
        if len(active_train_set) == 8:  # All are train objects
            table_oidxs = {1: active_train_set[0:4], 2: active_train_set[4:8], 3: None}
        else:  # Table 1 test objects, Table 2 train objects
            table_oidxs = {1: active_test_set[:], 2: active_train_set[:]}
        rospy.init_node('phm_node')
        print("WARNING: ensure robot is facing Table 2 on startup!")
        io = IO.RobotIO(table_oidxs, 2, image_path)
        use_shorter_utterances = True
    else:
        io = None  # won't be executed due to asserts
    print("main: ... done")

    # Normal operation.
    if init_phase == 0:
        # Instantiate an Agent.
        print("main: instantiating Agent...")
        a = Agent.Agent(p, g, io, active_train_set, no_clarify=no_clarify,
                        use_shorter_utterances=use_shorter_utterances,
                        word_neighbors_to_consider_as_synonyms=max_syn_qs,
                        max_perception_subdialog_qs=max_opp_qs)
        print("main: ... done")

        # Start a dialog.
        perception_labels_requested = []
        action_confirmed_per_dialog = []
        utterances_by_role_per_dialog = []
        parser_timeouts_per_dialog = []
        grounder_timeouts_per_dialog = []
        for _ in range(num_dialogs):
            print("main: running command dialog...")
            action_confirmed, user_utterances_by_role, parser_timeouts, grounder_timeouts = \
                a.start_action_dialog(perception_labels_requested=perception_labels_requested)
            action_confirmed_per_dialog.append(action_confirmed)
            utterances_by_role_per_dialog.append(user_utterances_by_role)
            parser_timeouts_per_dialog.append(parser_timeouts)
            grounder_timeouts_per_dialog.append(grounder_timeouts)
            print("main: ... done; got action " + str(action_confirmed))

            # Write out new information gleaned from this user after every dialog.
            if uid is not None:  # DEBUG
                print("main: writing new information from dialog(s) to file...")
                fn = os.path.join(data_dir, uid + ".pickle")
                d = [action_confirmed_per_dialog, utterances_by_role_per_dialog,
                     a.new_perceptual_labels, a.perceptual_pred_synonymy,
                     parser_timeouts_per_dialog, grounder_timeouts_per_dialog]
                with open(fn, 'wb') as f:
                    pickle.dump(d, f)
                print("main: ... done; wrote data d = " + str(d))

    # Just ask the user for a few rephrases of the command.
    else:
        print("main: starting init phase dialog...")
        for nd in range(num_dialogs):
            io.say_to_user("What should I do?")
            _ = io.get_from_user()
            for ip in range(init_phase - 1):
                io.say_to_user("What's another way you could phrase that command?")
                _ = io.get_from_user()
            io.perform_action({'action': 'init_phase'})
        print("main: ... done")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--parser_fn', type=str, required=False,
                        help="a parser pickle to load")
    parser.add_argument('--word_embeddings_fn', type=str, required=False,
                        help="fresh word embeddings to deal with gensim version differences")
    parser.add_argument('--io_type', type=str, required=True,
                        help="one of 'keyboard' or 'server'")
    parser.add_argument('--write_classifiers', type=int, required=False, default=0,
                        help="whether to write loaded/trained perception classifiers back to disk")
    parser.add_argument('--grounder_fn', type=str, required=False,
                        help="a grounder pickle to load; if not provided, a new one will be instantiated")
    parser.add_argument('--kb_static_facts_fn', type=str, required=False,
                        help="static facts file for the knowledge base")
    parser.add_argument('--kb_perception_source_dir', type=str, required=False,
                        help="perception source directory for knowledge base")
    parser.add_argument('--kb_perception_feature_dir', type=str, required=False,
                        help="perception feature directory for knowledge base")
    parser.add_argument('--active_test_set', type=str, required=False,
                        help="objects to consider possibilities for grounding; " +
                             "excluded from perception classifier training")
    parser.add_argument('--active_train_set', type=str, required=False, default=None,
                        help="objects to consider 'local' and able to be queried by opportunistic active learning")
    parser.add_argument('--uid', type=str, required=False,
                        help="for ServerIO")
    parser.add_argument('--data_dir', type=str, required=False,
                        help="for writing out information gathered during this dialog")
    parser.add_argument('--client_dir', type=str, required=False,
                        help="for ServerIO")
    parser.add_argument('--spin_time', type=int, required=False, default=1,
                        help="for ServerIO")
    parser.add_argument('--num_dialogs', type=int, required=False, default=1,
                        help="number of times to call start_action_dialog")
    parser.add_argument('--init_phase', type=int, required=False, default=0,
                        help="don't actually launch an agent; just ask for the specified number of responses")
    parser.add_argument('--max_syn_qs', type=int, required=False, default=3,
                        help="the maximum number of synonym neighbors to ask about")
    parser.add_argument('--max_opp_qs', type=int, required=False, default=5,
                        help="the maximum number of perception questions to ask")
    parser.add_argument('--image_path', type=str, required=False,
                        help="filepath to the directory where object images live")
    parser.add_argument('--no_clarify', type=str, required=False,
                        help="comma-separated list of roles not to clarify during dialog")
    args = parser.parse_args()
    for k, v in vars(args).items():
        globals()['FLAGS_%s' % k] = v
    main()
