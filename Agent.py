#!/usr/bin/env python
__author__ = 'jesse'

import copy
import math
import numpy as np
import operator
import os
import pickle
import random
import signal


class Agent:

    # Takes an instantiated, trained parser, a knowledge base grounder, an input/output instance, and
    # a (possibly empty) list of oidxs to be considered active for perceptual dialog questions.
    # The optional no_clarify argument can be a list of roles which the agent does not use clarification
    # dialog questions to confirm, but rather takes the current maximum belief as the correct argument
    # when sampling from the belief state.
    def __init__(self, parser, grounder, io, active_train_set, no_clarify=None,
                 use_shorter_utterances=False,  # useful for rendering speech on robot
                 word_neighbors_to_consider_as_synonyms=3,  # how many lexicon items to beam through for new pred
                 max_perception_subdialog_qs=3,  # based on CORL17 control condition; vetted down from 5
                 max_ask_before_enumeration=2):  # max times to ask the same question before using an enumeration backoff
        # random.seed(27)  # (adj for demo)
        # np.random.seed(seed=27)  # (adj for demo)
        self.parser = parser
        self.grounder = grounder
        self.io = io
        self.active_train_set = active_train_set
        self.use_shorter_utterances = use_shorter_utterances
        self.no_clarify = [] if no_clarify is None else no_clarify

        # hyperparameters
        self.parse_beam = 1
        self.threshold_to_accept_role = 1.0  # include role filler in questions above this threshold
        self.belief_update_rate = 0.5  # interpolation between belief state and grounding state
        self.threshold_to_accept_perceptual_conf = 0.7  # per perceptual predicate, e.g. 0.7*0.7 for two
        self.none_start_mass_factor = 1  # how much None mass per role versus all else; if 1, 50/50, if 9, 9 None to 1 else
        self.max_perception_subdialog_qs = max_perception_subdialog_qs
        self.max_ask_before_enumeration = max_ask_before_enumeration
        self.word_neighbors_to_consider_as_synonyms = word_neighbors_to_consider_as_synonyms
        self.budget_for_parsing = 15  # how many seconds we allow the parser
        self.budget_for_grounding = 10  # how many seconds we allow the grounder
        self.latent_forms_to_consider_for_induction = 32  # maximum parses to consider for grounding during induction
        # self.get_novel_question_beam = 10  # how many times to sample for a new question before giving up if identical

        # static information about expected actions and their arguments
        self.roles = ['action', 'patient', 'recipient', 'source', 'goal']
        self.actions = ['walk', 'bring', 'move']
        # expected argument types per action
        self.action_args = {'walk': {'goal': ['l']},
                            'bring': {'patient': ['i'], 'recipient': ['p']},
                            'move': {'patient': ['i'], 'source': ['l'], 'goal': ['l']}}

        self.action_belief_state = None  # maintained during action dialogs to track action, patient, recipient

        # pairs of [utterance, grounded SemanticNode] induced from conversations
        self.induced_utterance_grounding_pairs = []

        # pairs of (pred, oidx, label) gathered during perceptual sub-dialogs
        # We use pred as a str instead of its id to make collapsing labels across users easier later.
        self.new_perceptual_labels = []
        # pairs of (pred, pred, syn) for syn bool gathered during perceptual sub-dialogs
        self.perceptual_pred_synonymy = []

        # track parsing and grounding timeouts.
        self.parser_timeouts = 0
        self.grounder_timeouts = 0

    # Start a new action dialog from utterance u given by a user.
    # Clarifies the arguments of u until the action is confirmed by the user.
    # perception_labels_requested - pairs of (pidx, oidx) labels already requested from user; modified in-place.
    # perform_action - whether to execute the action through IO or just return it.
    def start_action_dialog(self, perception_labels_requested,
                            perform_action=True):
        debug = False

        # Start with a count of 1.0 on each role being empty (of which only recipient can remain empty in the end).
        # Perform belief updates modeled after IJCAI'15 paper based on presence/absence of arguments in answers.
        # Action beliefs are sampled from a probability distribution drawn from this histogram of beliefs.
        # For the patient role, explicitly limit 'i' types to those in the grounder's active test set to avoid sampling
        # irrelevant items (the grounder only thinks about whether predicates apply to test set).
        self.action_belief_state = {'action': {a: 1.0 for a in self.actions},
                                    'patient': {p: 1.0 for p in self.parser.ontology.preds
                                                if ((self.parser.ontology.types[self.parser.ontology.entries[
                                                     self.parser.ontology.preds.index(p)]] in
                                                     self.action_args['bring']['patient'] or
                                                     self.parser.ontology.types[self.parser.ontology.entries[
                                                         self.parser.ontology.preds.index(p)]] in
                                                     self.action_args['move']['patient']) and
                                                    (self.parser.ontology.types[self.parser.ontology.entries[
                                                     self.parser.ontology.preds.index(p)]] != 'i' or
                                                     int(p.split('_')[1]) in self.grounder.active_test_set))},
                                    'recipient': {r: 1.0 for r in self.parser.ontology.preds
                                                  if self.parser.ontology.types[self.parser.ontology.entries[
                                                      self.parser.ontology.preds.index(r)]] in
                                                  self.action_args['bring']['recipient']},
                                    'source': {r: 1.0 for r in self.parser.ontology.preds
                                               if self.parser.ontology.types[self.parser.ontology.entries[
                                                   self.parser.ontology.preds.index(r)]] in
                                               self.action_args['move']['source']},
                                    'goal': {r: 1.0 for r in self.parser.ontology.preds
                                             if (self.parser.ontology.types[self.parser.ontology.entries[
                                                 self.parser.ontology.preds.index(r)]] in
                                                 self.action_args['walk']['goal'] or
                                                 self.parser.ontology.types[self.parser.ontology.entries[
                                                     self.parser.ontology.preds.index(r)]] in
                                                 self.action_args['move']['goal'])}}
        # question generation supports None action, but I think it's weird maybe so I removed it here
        for r in ['patient', 'recipient', 'source', 'goal']:
            # None starts with chunk of the probability mass to encourage clarification over instance checks.
            self.action_belief_state[r][None] = self.none_start_mass_factor * len(self.action_belief_state[r])
        for r in self.roles:
            self.action_belief_state[r] = self.make_distribution_from_positive_counts(self.action_belief_state[r])
        if debug:
            print ("start_action_dialog starting with blank action belief state: "
                   + str(self.action_belief_state))

        # Ask a follow up question based on the new belief state.
        # This continues until an action is chosen.
        user_utterances_by_role = {r: [] for r in self.roles + ['all']}  # to later induce grounding matches
        action_confirmed = {r: None for r in self.roles}
        first_utterance = True
        perception_subdialog_qs = 0  # track how many have been asked so far to disallow more.
        asked_role_repeat = {}  # count the number of times we've requested a role in an open-ended question.
        last_q = None
        self.parser_timeouts = 0
        self.grounder_timeouts = 0
        # last_rvs = None
        while (action_confirmed['action'] is None or
               None in [action_confirmed[r] for r in self.action_args[action_confirmed['action']].keys()]):

            # Determine what question to ask based on missing arguments in chosen action.
            if not first_utterance:
                # q = last_q
                # rvs = last_rvs
                action_chosen = self.sample_action_from_belief(action_confirmed, arg_max=True)
                q, role_asked, _, roles_in_q = self.get_question_from_sampled_action(
                        action_chosen, self.threshold_to_accept_role)
                rvs = {r: action_chosen[r][0] for r in self.roles if r in roles_in_q}

                # If we are about to ask a second instance confirmation, sample a new question
                # that asks for an open-ended clarification instead.
                if role_asked is not None and q == last_q:
                    action_chosen_open = {r: action_chosen[r] for r in self.roles}
                    action_chosen_open[role_asked] = (None, 0)
                    q, role_asked, _, roles_in_q = self.get_question_from_sampled_action(
                        action_chosen_open, self.threshold_to_accept_role)
                    rvs = {r: action_chosen[r][0] for r in self.roles if r in roles_in_q}

                # If our question is identidcal to the last, apologize to encourage rewording.
                if q == last_q:
                    self.io.say_to_user("Sorry, I didn't understand that.")
                
                # Implementation to get a novel question to avoid asking annoying repeats.
                # With enumeration backoff, allowing annoying repeats speeds up convergence, so it's fine.
                # times_sampled = 0
                # while (q == last_q and last_rvs == rvs and (q is None or "rephrase" not in q) and
                #        times_sampled < self.get_novel_question_beam):
                #     action_chosen = self.sample_action_from_belief(action_confirmed,
                #                                                    arg_max=True if times_sampled == 0 else False)
                #     q, role_asked, _, roles_in_q = self.get_question_from_sampled_action(
                #         action_chosen, self.threshold_to_accept_role)
                #     rvs = {r: action_chosen[r][0] for r in self.roles if r in roles_in_q}
                #     times_sampled += 1
                #     if debug:
                #         print "sampled q " + str(q)
                # last_q = q
                # last_rvs = rvs
                # if times_sampled == self.get_novel_question_beam:
                #     self.io.say_to_user("Sorry, I didn't understand that.")
            else:
                action_chosen = self.sample_action_from_belief(action_confirmed, arg_max=True)
                q = "What should I do?"
                role_asked = None
                roles_in_q = []
                rvs = {}
            first_utterance = False
            last_q = q

            # Ask question and get user response.
            if role_asked is None or (action_chosen[role_asked][0] is None or role_asked not in roles_in_q):
                conf_q = False

                # If this is not a confirmation question, note that we're asking an open-ended one since
                # we only allow up to a max number of open-ended repeats for a role before backing off to
                # an enumeration strategy to avoid annoying the user too much.
                if role_asked is not None:
                    if role_asked not in asked_role_repeat:
                        asked_role_repeat[role_asked] = 0
                    asked_role_repeat[role_asked] += 1
            else:
                conf_q = True

            # Confirmation yes/no question.
            if conf_q:
                ur = self.get_yes_no_from_user(q, rvs)
                action_confirmed = self.update_action_belief_from_confirmation(ur, action_confirmed,
                                                                               action_chosen, roles_in_q)

            # Open-ended response question.
            else:
                # Back off to an enumeration strategy if we're about to ask an open-ended question for the Nth time.
                if role_asked is not None and asked_role_repeat[role_asked] >= self.max_ask_before_enumeration + 1:
                    # We actually only need the strings of the belief state to do a confirmation update, which is nice!
                    enum_candidates_strs = [k for k, _ in sorted(self.action_belief_state[role_asked].items(), key=operator.itemgetter(1),
                                                                 reverse=True)
                                            if k is not None]  # Enumerate possible choices in current order of belief.

                    # Present these as options to user.
                    self.io.say_to_user_with_referents(q, rvs)  # Ask same open-ended question but show enumeration instead of open-ended text resp.
                    enum_ur = self.io.get_from_user_enum(enum_candidates_strs, role_asked)  # Show enumeration to user and have them select exactly one.
                    enum_chosen = {role_asked: [enum_ur, 1.]} # Full confidence to the selected choice.

                    # Do a confirmation update based on the user selection to solidify their choice in the action belief space.
                    action_confirmed = self.update_action_belief_from_confirmation('yes', action_confirmed, enum_chosen, [role_asked])

                else:
                    self.io.say_to_user_with_referents(q, rvs)
                    ur = self.io.get_from_user()

                    # Possible sub-dialog to clarify whether new words are perceptual and, possibly synonyms of existing
                    # neighbor words.
                    self.preprocess_utterance_for_new_predicates(ur)

                    # Get groundings and latent parse from utterance.
                    gprs, pr = self.parse_and_ground_utterance(ur)

                    # Start a sub-dialog to ask clarifying perceptual questions before continuing with slot-filling.
                    # If sub-dialog results in fewer than the maximum number of questions, allow asking off-topic
                    # questions in the style of CORL'17 paper to improve future interactions.
                    if role_asked == 'patient' or role_asked is None:
                        num_new_qs = 0
                        if self.active_train_set is not None:
                            if perception_subdialog_qs < self.max_perception_subdialog_qs:
                                num_new_qs += self.conduct_perception_subdialog(gprs, pr,
                                                                                self.max_perception_subdialog_qs,
                                                                                perception_labels_requested)
                                perception_subdialog_qs += num_new_qs
                            if perception_subdialog_qs < self.max_perception_subdialog_qs:
                                preface_msg = True if perception_subdialog_qs == 0 else False
                                num_new_qs += self.conduct_perception_subdialog(gprs, pr,
                                                                                self.max_perception_subdialog_qs -
                                                                                perception_subdialog_qs,
                                                                                perception_labels_requested,
                                                                                allow_off_topic_preds=True,
                                                                                preface_msg=preface_msg)
                                perception_subdialog_qs += num_new_qs
                        if num_new_qs > 0:
                            self.io.say_to_user("Thanks. Now, back to business.")

                            # Reground utterance from fresh classifier information.
                            if pr is not None:
                                gprs = self.ground_semantic_form(pr.node)

                    if role_asked is None:  # asked to repeat whole thing
                        user_utterances_by_role['all'].append(ur)
                        self.update_action_belief_from_groundings(gprs, self.roles)
                    # asked an open-ended question for a particular role (e.g. "where should i go?")
                    elif action_chosen[role_asked][0] is None or role_asked not in roles_in_q:
                        user_utterances_by_role[role_asked].append(ur)
                        self.update_action_belief_from_groundings(gprs, [role_asked])

            # Fill current_confirmed with any no_clarify roles by taking the current non-None max.
            # As in other max operations, considers all tied values and chooses one at random.
            # These role slots are re-filled after every confidence update, so they are the only clarification
            # slots that can be changed.
            for r in self.no_clarify:
                valid_entries = [entry for entry in self.action_belief_state[r]
                                 if entry is not None]
                dist = [self.action_belief_state[r][entry] for entry in valid_entries]
                s = sum(dist)
                dist = [dist[idx] / s for idx in range(len(dist))]
                max_idxs = [idx for idx in range(len(dist)) if dist[idx] == max(dist)]
                c = np.random.choice([valid_entries[idx] for idx in max_idxs], 1)
                action_confirmed[r] = c[0]

            if debug:
                print("start_action_dialog: updated action belief state: " + str(self.action_belief_state))

        # Induce utterance/grounding pairs from this conversation.
        # new_i_pairs = self.induce_utterance_grounding_pairs_from_conversation(user_utterances_by_role,
        #                                                                       action_confirmed)
        # self.induced_utterance_grounding_pairs.extend(new_i_pairs)

        # TODO: update SVMs with positive example from active test set
        # TODO: this is tricky since in live experiment these labels still have to be ignored
        # TODO: will have to do fold-by-fold training as usual
        # TODO: also tricky because without explicitly asking, the labels come from reverse-grounding,
        # TODO: which can be noisy and should be overwritten later on by explicit human conversation.

        # Perform the chosen action.
        if perform_action:
            self.io.perform_action(action_confirmed)

        # Return the chosen action and the user utterances by role from this dialog.
        return action_confirmed, user_utterances_by_role, self.parser_timeouts, self.grounder_timeouts

    # Given a dictionary of key -> value for positive values, return a dictionary over the same keys
    # with the value ssumming to 1.
    def make_distribution_from_positive_counts(self, d):
        assert True not in [True if d[k] < 0 else False for k in d.keys()]
        s = sum([d[k] for k in d.keys()])
        return {k: d[k] / float(s) for k in d.keys()}

    # While top grounding confidence does not pass perception threshold, ask a question that
    # strengthens an SVM involved in the current parse.
    # In effect, this can start a sub-dialog about perception, which, when resolved, returns to
    # the existing slot-filling dialog.
    # ur - the user response to the last question, which may contain perceptual predicates
    # gprs - groundings of parse from last response
    # pr - the associated latent parse
    # max_questions - the maximum number of questions to ask in this sub-dialog
    # labeled_tuples - a list of (pidx, oidx) tuples labeled by the user; modified in-place with new entries
    # allow_off_topic_preds - if flipped to true, considers all predicates, not just those in parse of utterance
    # returns - an integer, the number of questions asked
    def conduct_perception_subdialog(self, gprs, pr, max_questions, labeled_tuples,
                                     allow_off_topic_preds=False, preface_msg=True):
        debug = False

        num_qs = 0
        if len(gprs) > 0:

            perception_above_threshold = False
            top_conf = gprs[0][1]
            perceptual_pred_trees = self.get_parse_subtrees(pr.node, self.grounder.kb.perceptual_preds)
            if debug:
                print ("conduct_perception_subdialog: perceptual confidence " + str(top_conf) + " versus " +
                       "threshold " + str(self.threshold_to_accept_perceptual_conf) + " across " +
                       str(len(perceptual_pred_trees)) + " predicates")
            while (allow_off_topic_preds or not perception_above_threshold) and num_qs < max_questions:
                if (allow_off_topic_preds or
                        top_conf < math.pow(self.threshold_to_accept_perceptual_conf,
                                            len(perceptual_pred_trees))):
                    if debug:
                        print ("conduct_perception_subdialog: perceptual confidence " + str(top_conf) +
                               " below threshold or we are allowing off-topic predicates; " +
                               "entering dialog to strengthen perceptual classifiers")

                    # Sub-dialog to ask perceptual predicate questions about objects in the active training
                    # set until confidence threshold is reached or no more information can be gained
                    # from the objects in the active training set.

                    # For current SVMs, calculate the least-reliable predicates when applied to test objects.
                    # Additionally record current confidences against active training set objects.
                    pred_test_conf = {}  # from predicates to confidence sums
                    pred_train_conf = {}  # from predicates to active training idx oidx to confidences
                    if allow_off_topic_preds:
                        preds_to_consider = self.grounder.kb.pc.predicates[:]
                    else:
                        preds_to_consider = [self.parser.ontology.preds[root.idx]
                                             for root in perceptual_pred_trees]
                    if len(preds_to_consider) == 0:  # no further preds to consider
                        return num_qs
                    pred_to_surface = {}
                    for pred in preds_to_consider:
                        pidx = self.grounder.kb.pc.predicates.index(pred)

                        # Calculate the surface form to use with this pred.
                        # We look at the raw count score for the sem | sf since the parameter vector is normalized
                        # given the surface form, but we're looking for the max across surface forms.
                        sems_with_pred = [sem_idx for sem_idx in range(len(self.parser.lexicon.semantic_forms))
                                          if len(self.get_parse_subtrees(self.parser.lexicon.semantic_forms[sem_idx],
                                                                         [pred])) > 0]
                        sfs_with_sems = [(sf_idx, sem_idx) for sf_idx in range(len(self.parser.lexicon.surface_forms))
                                         for sem_idx in self.parser.lexicon.entries[sf_idx]
                                         if sem_idx in sems_with_pred]
                        sf_sem_scores = [self.parser.theta._lexicon_entry_given_token_counts[(sem_idx, sf_idx)] if
                                         (sem_idx, sf_idx) in self.parser.theta._lexicon_entry_given_token_counts else 0
                                         for sem_idx, sf_idx in sfs_with_sems]
                        best_sf_sem_score = max(sf_sem_scores)
                        pred_to_surface[pred] = self.parser.lexicon.surface_forms[
                            sfs_with_sems[sf_sem_scores.index(best_sf_sem_score)][0]]

                        test_conf = 0
                        for oidx in self.grounder.active_test_set:
                            pos_conf, neg_conf = self.grounder.kb.query((pred, 'oidx_' + str(oidx)))
                            test_conf += max(pos_conf, neg_conf)
                        pred_test_conf[pred] = test_conf / len(self.grounder.active_test_set)

                        pred_train_conf[pred] = []
                        for oidx in self.active_train_set:
                            if (pidx, oidx) not in labeled_tuples:
                                pos_conf, neg_conf = self.grounder.kb.query((pred, 'oidx_' + str(oidx)))
                                pred_train_conf[pred].append(max(pos_conf, neg_conf))
                                if pred_train_conf[pred][-1] < 0:
                                    pred_train_conf[pred][-1] = 0.
                                elif pred_train_conf[pred][-1] > 1:
                                    pred_train_conf[pred][-1] = 1.
                            else:
                                pred_train_conf[pred].append(1)
                    if debug:
                        print ("conduct_perception_subdialog: examined classifiers to get pred_test_conf: " +
                               str(pred_test_conf) + " and pred_train_conf: " + str(pred_train_conf) +
                               " for active train set " + str(self.active_train_set))

                    # Examine preds probabilistically for least test confidence until we reach one for which we can
                    # formulate a useful question against the active training set objects. If all of the
                    # active training set objects have been labeled or have total confidence already
                    # for every predicate, the sub-dialog can't be productive and ends.
                    q = None
                    rvs = {}
                    q_type = None
                    perception_pidx = None
                    pred = None
                    # Order predicates weighted by their negative test confidence as a probability.
                    sum_inv_test_conf = sum([1 - pred_test_conf[pred] for pred in preds_to_consider])
                    pred_probs = [(1 - pred_test_conf[pred]) / sum_inv_test_conf for pred in preds_to_consider]
                    # Clamp the probabilities to [0, 1] by hand since the floating point ops sometimes drift outside.
                    pred_probs = [prob if 0. < prob < 1. else (0. if prob < 0. else 1.)
                                  for prob in pred_probs]
                    if debug:
                        print ("conduct_perception_subdialog: resulting pred probs " + str(pred_probs) +
                               " for predicates " + str(preds_to_consider))
                    nonzero_to_consider = [preds_to_consider[idx] for idx in range(len(pred_probs))
                                           if pred_probs[idx] > 0]
                    nonzero_probs = [pred_probs[idx] for idx in range(len(pred_probs))
                                     if pred_probs[idx] > 0]
                    sampled_preds_to_ask = np.random.choice(nonzero_to_consider, len(nonzero_to_consider),
                                                            replace=False, p=nonzero_probs)
                    for pred in sampled_preds_to_ask:
                        if debug:
                            print ("conduct_perception_subdialog: sampled pred '" + pred +
                                   "' with pred_train_conf " + str(pred_train_conf[pred]))

                        # If at least one active training object is unlabeled or unconfident
                        if sum(pred_train_conf[pred]) < len(self.active_train_set):
                            perception_pidx = self.grounder.kb.pc.predicates.index(pred)

                            # If all objects are below the perception threshold, ask for label we have least of.
                            if min(pred_train_conf[pred]) < self.threshold_to_accept_perceptual_conf:
                                ls = [l for _p, _o, l in self.grounder.kb.pc.labels if _p == perception_pidx
                                      and _o not in self.grounder.active_test_set]
                                if ls.count(1) <= ls.count(0):  # more negative labels or labels are equal
                                    if self.use_shorter_utterances:
                                        q = ("Show me an object you could use the word '" + pred_to_surface[pred] +
                                             "' when describing, or shake your head.")
                                    else:
                                        q = ("Among these nearby objects, could you show me one you would use the " +
                                             "word '" + pred_to_surface[pred] + "' when describing, or shake your " +
                                             "head if there are none?")
                                    q_type = 'pos'
                                else:  # more positive labels
                                    if self.use_shorter_utterances:
                                        q = ("Show me an object you could not use the word '" + pred_to_surface[pred] +
                                             "' when describing, or shake your head.")
                                    else:
                                        q = ("Among these nearby objects, could you show me one you could not use " +
                                             "the word '" + pred_to_surface[pred] + "' when describing, or shake " +
                                             "your head if you could use " + "'" + pred_to_surface[pred] +
                                             "' when describing all of them?")
                                    q_type = 'neg'

                            # Else, ask for the label of the (sampled) least-confident object.
                            else:
                                sum_inv_train_conf = sum([1 - pred_train_conf[pred][idx]
                                                          for idx in range(len(pred_train_conf[pred]))])
                                pred_train_conf_idx = np.random.choice(range(len(pred_train_conf[pred])), 1,
                                                                       p=[(1 - pred_train_conf[pred][idx]) /
                                                                          sum_inv_train_conf
                                                                          for idx in
                                                                          range(len(pred_train_conf[pred]))])[0]
                                if debug:
                                    print ("conduct_perception_subdialog: sampled idx " + str(pred_train_conf_idx) +
                                           " out of confidences " + str(pred_train_conf[pred]))
                                oidx = self.active_train_set[pred_train_conf_idx]
                                q = ("Would you use the word '" + pred_to_surface[pred] +
                                     "' when describing <p>this</p> object?")
                                rvs['patient'] = 'oidx_' + str(oidx)
                                q_type = oidx

                            # Ask the question we settled on.
                            break

                        # Nothing more to be gained by asking questions about the active training set
                        # with respect to this predicate.
                        else:
                            continue

                    # If we didn't settle on a question, all active training set objects have been labeled
                    # for every predicate of interest, so this sub-dialog can't get us anywhere.
                    if q is None:
                        break

                    # If q is not None, we're going to engage in the sub-dialog.
                    if num_qs == 0 and preface_msg:
                        if self.use_shorter_utterances:
                            self.io.say_to_user("I'm still learning the meanings of some words.")
                        else:
                            self.io.say_to_user("I'm still learning the meanings of some words. I'm going to ask you " +
                                                "a few questions about these nearby objects before we continue.")

                    # Ask the question and get a user response.
                    if q_type == 'pos' or q_type == 'neg':
                        self.io.say_to_user_with_referents(q, rvs)
                        sub_ur = -1
                        while sub_ur is not None and sub_ur not in self.active_train_set:
                            sub_ur = self.io.get_oidx_from_user(self.active_train_set)
                    else:  # i.e. q_type is a particular oidx atom we asked a yes/no about
                        sub_ur = self.get_yes_no_from_user(q, rvs)
                    num_qs += 1

                    # Update perceptual classifiers from user response.
                    upidxs = []
                    uoidxs = []
                    ulabels = []
                    if q_type == 'pos':  # response is expected to be an oidx or 'none' (e.g. None)
                        if sub_ur is None:  # None, so every object in active train is a negative example
                            upidxs = [perception_pidx] * len(self.active_train_set)
                            uoidxs = self.active_train_set
                            ulabels = [0] * len(self.active_train_set)
                            labeled_tuples.extend([(perception_pidx, oidx) for oidx in self.active_train_set])
                            self.new_perceptual_labels.extend([(pred, oidx, 0) for oidx in self.active_train_set])
                        else:  # an oidx of a positive example
                            upidxs = [perception_pidx]
                            uoidxs = [sub_ur]
                            ulabels = [1]
                            labeled_tuples.append((perception_pidx, sub_ur))
                            e = (pred, sub_ur, 1)
                            if e not in self.new_perceptual_labels:
                                self.new_perceptual_labels.append(e)
                            else:  # if the user gives the same answer twice, just move on.
                                num_qs += self.max_perception_subdialog_qs
                    elif q_type == 'neg':  # response is expected to be an oidx or 'all' (e.g. None)
                        if sub_ur is None:  # None, so every object in active train set is a positive example
                            upidxs = [perception_pidx] * len(self.active_train_set)
                            uoidxs = self.active_train_set
                            ulabels = [1] * len(self.active_train_set)
                            labeled_tuples.extend([(perception_pidx, oidx) for oidx in self.active_train_set])
                            self.new_perceptual_labels.extend([(pred, oidx, 1) for oidx in self.active_train_set])
                        else:  # an oidx of a negative example
                            upidxs = [perception_pidx]
                            uoidxs = [sub_ur]
                            ulabels = [0]
                            labeled_tuples.append((perception_pidx, sub_ur))
                            e = (pred, sub_ur, 0)
                            if e not in self.new_perceptual_labels:
                                self.new_perceptual_labels.append(e)
                            else:  # if the user gives the same answer twice, just move on.
                                num_qs += self.max_perception_subdialog_qs
                    else:  # response is expected to be a confirmation yes/no
                        if sub_ur == 'yes':
                            upidxs = [perception_pidx]
                            uoidxs = [q_type]
                            ulabels = [1]
                            labeled_tuples.append((perception_pidx, q_type))
                            self.new_perceptual_labels.append((pred, q_type, 1))
                        elif sub_ur == 'no':
                            upidxs = [perception_pidx]
                            uoidxs = [q_type]
                            ulabels = [0]
                            labeled_tuples.append((perception_pidx, q_type))
                            self.new_perceptual_labels.append((pred, q_type, 0))
                    if debug:
                        print ("conduct_perception_subdialog: updating classifiers with upidxs " + str(upidxs) +
                               ", uoidxs " + str(uoidxs) + ", ulabels " + str(ulabels))
                    self.grounder.kb.pc.update_classifiers([], upidxs, uoidxs, ulabels)

                    # Re-ground with updated classifiers.
                    gprs = self.ground_semantic_form(pr.node)
                    if len(gprs) > 0:
                        top_conf = gprs[0][1]

                else:
                    perception_above_threshold = True

        return num_qs

    # Given a user utterance, pass over the tokens to identify potential new predicates. This can initiate
    # a sub-dialog in which the user is asked whether a word requires perceiving the real world, and then whether
    # it means the same thing as a few neighboring words. This dialog's length is limited linearly with respect
    # to the number of words in the utterance, but could be long for many new predicates.
    def preprocess_utterance_for_new_predicates(self, u):
        debug = False
        if debug:
            print ("preprocess_utterance_for_new_predicates: called with utterance " + u)

        tks = u.strip().split()
        for tkidx in range(len(tks)):
            tk = tks[tkidx]
            if tk not in self.parser.lexicon.surface_forms:  # this token hasn't been analyzed by the parser
                if debug:
                    print ("preprocess_utterance_for_new_predicates: token '" + tk + "' has not been " +
                           "added to the parser's lexicon yet")

                # Get all the neighbors in order based on word embedding distances for this word.
                nn = self.parser.lexicon.get_lexicon_word_embedding_neighbors(
                    tk, self.word_neighbors_to_consider_as_synonyms)

                # Beam through neighbors to determine which, if any, are perceptual
                perceptual_neighbors = {}  # from surface forms to parse subtress
                for idx in range(len(nn)):
                    nsfidx, _ = nn[idx]

                    # Determine if lexical entries for the neighbor contain perceptual predicates.
                    for sem_idx in self.parser.lexicon.entries[nsfidx]:
                        psts = self.get_parse_subtrees(self.parser.lexicon.semantic_forms[sem_idx],
                                                       self.grounder.kb.perceptual_preds)
                        if len(psts) > 0:
                            if nsfidx not in perceptual_neighbors:
                                perceptual_neighbors[nsfidx] = []
                            perceptual_neighbors[nsfidx].extend(psts)
                if debug:
                    print ("preprocess_utterance_for_new_predicates: identified perceptual neighbors: " +
                           str(perceptual_neighbors))

                # If there are perceptual neighbors, confirm with the user that this new word requires perception.
                # If there were no neighbors at all, the word isn't in the embedding space and might be a brand name
                # (e.g. pringles) that we could consider perceptual by adding an "or len(nn) == 0".
                if len(perceptual_neighbors.keys()) > 0:
                    if self.use_shorter_utterances:
                        q = "Does '" + tk + "' refer to a property of an object?"
                    else:
                        q = ("I haven't heard the word '" + tk + "' before. Does it refer to properties of " +
                             "things, like a color, shape, or weight?")
                    c = self.get_yes_no_from_user(q)
                    if c == 'yes':

                        # Ask about each neighbor in the order we found them, corresponding to closest distances.
                        synonym_identified = None
                        for nsfidx in perceptual_neighbors.keys():

                            _q = ("Does '" + tk + "' mean the same thing as '" +
                                  self.parser.lexicon.surface_forms[nsfidx] + "'?")
                            _c = self.get_yes_no_from_user(_q)

                            # The new word tk is a synonym of the neighbor, so share lexical entries between them.
                            if _c == 'yes':
                                synonym_identified = [nsfidx, perceptual_neighbors[nsfidx]]
                                self.perceptual_pred_synonymy.append((tk, self.parser.lexicon.surface_forms[nsfidx],
                                                                      True))
                                break
                            # The new word is not a synonym according to this user.
                            else:
                                self.perceptual_pred_synonymy.append((tk, self.parser.lexicon.surface_forms[nsfidx],
                                                                      False))

                        # Whether we identified a synonym or not, we need to determine whether this word is being
                        # Used as an adjective or a noun, which we can do based on its position in the utterance.
                        # TODO: make checking for adjective a flag depending on whether we're using a bare noun-only
                        # TODO: parser instead of the current hard fix to that.
                        tk_probably_adjective = self.is_token_adjective(tkidx, tks)
                        if debug:
                            # print ("preprocess_utterance_for_new_predicates: examined following token and guessed " +
                            #        " that '" + tk + "'s probably adjective value is " + str(tk_probably_adjective))
                            print ("preprocess_utterance_for_new_predicates: examined following token and guessed " +
                                   " that '" + tk + "'s probably adjective value is " + str(False))

                        # Add new lexical entries for this fresh perceptual token.
                        # self.add_new_perceptual_lexical_entries(tk, tk_probably_adjective, synonym_identified)
                        self.add_new_perceptual_lexical_entries(tk, False, synonym_identified)

                        # TODO: these are also part of the bare-noun hard fix.
                        self.parser.type_raise_bare_nouns()  # should only affect new nouns
                        self.parser.theta.update_probabilities()  # because the above adds new entries

    # Add new lexical entries from a perceptual token.
    # tk - the string token to be added
    # tk_probably_adjective - whether the new token should be treated as an adjective entry
    # synonym_identified - a tuple of the [surface_form_idx, semantic entries for that surface form] flagged syn w tk
    def add_new_perceptual_lexical_entries(self, tk, tk_probably_adjective, synonym_identified, known_ont_pred=None,
                                           debug=False):
        assert synonym_identified is None or known_ont_pred is None

        # Prepare to add new entries.
        noun_cat_idx = self.parser.lexicon.categories.index('N')  # assumed to exist
        adj_cat_idx = self.parser.lexicon.categories.index([noun_cat_idx, 1, noun_cat_idx])  # i.e. N/N
        item_type_idx = self.parser.ontology.types.index('i')
        bool_type_idx = self.parser.ontology.types.index('t')
        pred_type_idx = self.parser.ontology.types.index([item_type_idx, bool_type_idx])
        if tk_probably_adjective:
            cat_to_match = adj_cat_idx
            sem_prefix = "lambda P:<i,t>.(and("
            sem_suffix = ", P))"
        else:
            cat_to_match = noun_cat_idx
            sem_prefix = ""
            sem_suffix = ""

        # Add synonym lexical entry for appropriate form (adj or noun) of identified synonym,
        # or create one if necessary.
        # If the synonym has more than one N or N/N entry (as appropriate), both will be added.
        if synonym_identified is not None:
            nsfidx, psts = synonym_identified
            if debug:
                print ("add_new_perceptual_lexical_entries: " +
                       "searching for synonym category matches")

            synonym_had_category_match = False
            for sem_idx in self.parser.lexicon.entries[nsfidx]:
                if self.parser.lexicon.semantic_forms[sem_idx].category == cat_to_match:
                    if tk not in self.parser.lexicon.surface_forms:
                        self.parser.lexicon.surface_forms.append(tk)
                        self.parser.lexicon.entries.append([])
                    sfidx = self.parser.lexicon.surface_forms.index(tk)
                    if sfidx not in self.parser.theta._skipwords_given_surface_form:
                        self.parser.theta._skipwords_given_surface_form[sfidx] = \
                            self.parser.theta._skipwords_given_surface_form[nsfidx]
                    self.parser.lexicon.neighbor_surface_forms.append(sfidx)
                    self.parser.lexicon.entries[sfidx].append(sem_idx)
                    self.parser.theta._lexicon_entry_given_token_counts[(sem_idx, sfidx)] = \
                        self.parser.theta._lexicon_entry_given_token_counts[(sem_idx, nsfidx)]
                    self.parser.theta.update_probabilities()
                    synonym_had_category_match = True
                    if debug:
                        print ("add_new_perceptual_lexical_entries: added a lexical entry" +
                               " due to category match: " +
                               self.parser.print_parse(self.parser.lexicon.semantic_forms[sem_idx],
                                                       True))

            # Create a new adjective entry N/N : lambda P.(synonympred, P) or N : synonympred
            # All perception predicates associated with entries in the chosen synonym generate entries.
            if not synonym_had_category_match:
                if debug:
                    print ("add_new_perceptual_lexical_entries: no category match for synonym")
                for pst in psts:  # trees with candidate synonym preds in them somewhere
                    candidate_preds = [p for p in self.scrape_preds_from_parse(pst)
                                       if p in self.grounder.kb.perceptual_preds]
                    for cpr in candidate_preds:
                        s = sem_prefix + cpr + sem_suffix
                        sem = self.parser.lexicon.read_semantic_form_from_str(s, cat_to_match, None, [])
                        if tk not in self.parser.lexicon.surface_forms:
                            self.parser.lexicon.surface_forms.append(tk)
                            self.parser.lexicon.entries.append([])
                        sfidx = self.parser.lexicon.surface_forms.index(tk)
                        self.parser.lexicon.neighbor_surface_forms.append(sfidx)
                        if sfidx not in self.parser.theta._skipwords_given_surface_form:
                            self.parser.theta._skipwords_given_surface_form[sfidx] = \
                                self.parser.theta._skipwords_given_surface_form[nsfidx]
                        if sem not in self.parser.lexicon.semantic_forms:
                            self.parser.lexicon.semantic_forms.append(sem)
                        sem_idx = self.parser.lexicon.semantic_forms.index(sem)
                        self.parser.lexicon.entries[sfidx].append(sem_idx)
                        self.parser.theta._lexicon_entry_given_token_counts[(sem_idx, sfidx)] = \
                            self.parser.theta.lexicon_weight  # fresh entry not borrowing neighbor value
                        if debug:
                            print ("add_new_perceptual_lexical_entries: created lexical entry " +
                                   "for candidate pred extracted from synonym trees: " +
                                   self.parser.print_parse(sem, True))

            ont_tk = None

        # No identified synonym, so we instead have to create a new ontological predicate
        # and then add a lexical entry pointing to it as a N or N/N entry, as appropriate.
        else:
            if debug:
                print ("add_new_perceptual_lexical_entries: no synonym found, so adding new " +
                       "ontological concept for '" + tk + "'")

            # Create a new ontological predicate to represent the new perceptual concept.
            if known_ont_pred is not None:
                ont_tk = known_ont_pred
            elif tk in self.parser.ontology.preds:
                i = 0
                while tk + "_" + str(i) in self.parser.ontology.preds:
                    i += 1
                ont_tk = tk + "_" + str(i)
            else:
                ont_tk = tk
            self.parser.ontology.preds.append(ont_tk)
            self.parser.ontology.entries.append(pred_type_idx)
            self.parser.ontology.num_args.append(self.parser.ontology.calc_num_pred_args(
                len(self.parser.ontology.preds) - 1))

            # Create a new perceptual predicate to represent the new perceptual concept.
            if ont_tk not in self.grounder.kb.pc.predicates:
                self.grounder.kb.pc.update_classifiers([ont_tk], [], [], [])  # blank concept
                if debug:
                    print ("add_new_perceptual_lexical_entries: updated perception classifiers with" +
                           " new concept '" + ont_tk + "'")

            # Create a lexical entry corresponding to the newly-acquired perceptual concept.
            s = sem_prefix + ont_tk + sem_suffix
            if debug:
                print ("add_new_perceptual_lexical_entries: adding lexical entry '" + s + "'")
            sem = self.parser.lexicon.read_semantic_form_from_str(s, cat_to_match, None, [])
            if tk not in self.parser.lexicon.surface_forms:
                self.parser.lexicon.surface_forms.append(tk)
                self.parser.lexicon.entries.append([])
            sfidx = self.parser.lexicon.surface_forms.index(tk)
            if sfidx not in self.parser.theta._skipwords_given_surface_form:
                self.parser.theta._skipwords_given_surface_form[sfidx] =\
                    - (self.parser.theta.lexicon_weight)  # * 2 new for demonstration
            if sem not in self.parser.lexicon.semantic_forms:
                self.parser.lexicon.semantic_forms.append(sem)
            sem_idx = self.parser.lexicon.semantic_forms.index(sem)
            self.parser.lexicon.entries[sfidx].append(sem_idx)
            self.parser.theta._lexicon_entry_given_token_counts[(sem_idx, sfidx)] = \
                self.parser.theta.lexicon_weight  # fresh entry not borrowing neighbor value
            if debug:
                print ("add_new_perceptual_lexical_entries: created lexical entry for new " +
                       "perceptual concept: " + self.parser.print_parse(sem, True))

        # Since entries may have been added, update probabilities before any more parsing is done.
        self.parser.theta.update_probabilities()

        # Return the new ontological concept string, if any, produced by this procedure.
        return ont_tk

    # We assume if the token to the right of tk is the end of utterance or a non-perceptual
    # word based on our lexicon (or appropriate beam search), it's a noun. Otherwise, it is an adjective.
    # tkidx - the index of the token in question
    # tks - the sequence of tokens
    def is_token_adjective(self, tkidx, tks):
        if tkidx < len(tks) - 1 and self.is_token_perceptual(tks[tkidx + 1]):
            return True
        else:
            return False

    # If word is last or has non-perceptual to the right and perceptual to the left, probably a noun.
    # If the word to the left is 'the'/'a' that picks out an object, etc., also probably a noun.
    # tkidx - the index of the token in question
    # tks - the sequence of tokens
    def is_token_noun(self, tkidx, tks):
        if ((tkidx == len(tks) - 1 or not self.is_token_perceptual(tks[tkidx + 1])) and
                (tkidx == 0 or self.is_token_perceptual(tks[tkidx - 1]))):
            return True
        elif tkidx > 0 and (tkidx == len(tks) - 1 or tks[tkidx + 1] in self.parser.lexicon.surface_forms):
            # Check whether left of this is 'the'/'a' and right is a -known- word that isn't perceptual.
            if tks[tkidx - 1] in self.parser.lexicon.surface_forms:
                sts = []
                for sf_idx in self.parser.lexicon.entries[self.parser.lexicon.surface_forms.index(tks[tkidx - 1])]:
                    sts.extend(self.get_parse_subtrees(self.parser.lexicon.semantic_forms[sf_idx], ['a_i']))
                if len(sts) > 0:
                    return True
        return False

    # tk - the token in question
    def is_token_perceptual(self, tk):
        candidate_semantic_forms = []
        if tk in self.parser.lexicon.surface_forms:
            candidate_semantic_forms.extend([self.parser.lexicon.semantic_forms[sem_idx]
                                             for sem_idx in self.parser.lexicon.entries[
                self.parser.lexicon.surface_forms.index(tk)]])
        else:
            nnn = self.parser.lexicon.get_lexicon_word_embedding_neighbors(
                tk, self.word_neighbors_to_consider_as_synonyms)
            for nsfidx, _ in nnn:
                candidate_semantic_forms.extend([self.parser.lexicon.semantic_forms[sem_idx]
                                                 for sem_idx in self.parser.lexicon.entries[nsfidx]])
        psts = []
        for ncsf in candidate_semantic_forms:
            psts.extend(self.get_parse_subtrees(ncsf, self.grounder.kb.perceptual_preds))
        # next word is probably not perceptual
        if len(psts) > 0:
            return True
        else:
            return False

    # Given an initial query, keep pestering the user for a response we can parse into a yes/no confirmation
    # until it's given.
    def get_yes_no_from_user(self, q, rvs=None):

        if rvs is None:
            self.io.say_to_user(q)
        else:
            self.io.say_to_user_with_referents(q, rvs)
        while True:
            u = self.io.get_from_user()
            gps, _ = self.parse_and_ground_utterance(u)
            for g, _ in gps:
                if type(g) is not bool and g.type == self.parser.ontology.types.index('c'):
                    if g.idx == self.parser.ontology.preds.index('yes'):
                        return 'yes'
                    elif g.idx == self.parser.ontology.preds.index('no'):
                        return 'no'
            self.io.say_to_user("Sorry, I am confused and just need a 'yes' or 'no' response for now.")
            if rvs is None:
                self.io.say_to_user(q)
            else:
                self.io.say_to_user_with_referents(q, rvs)

    # g is a string of values 'yes'|'no'
    def update_action_belief_from_confirmation(self, g, action_confirmed, action_chosen, roles_in_q):
        debug = False

        if debug:
            print ("update_action_belief_from_confirmation: confirmation response str " +
                   g + " with roles_in_q " + str(roles_in_q))
        if g == 'yes':
            for r in roles_in_q:
                action_confirmed[r] = action_chosen[r][0]
                if debug:
                    print ("update_action_belief_from_confirmation: confirmed role " + r + " with argument " +
                           action_chosen[r][0])
        elif g == 'no':
            if len(roles_in_q) > 0:

                # Create a distribution from this negative confirmation with zero confidence in all
                # members of mentioned roles, and uniform confidence in un-mentioned, to be interpolated
                # with the existing belief state.
                gd = {r: {a: 0.0 for a in self.action_belief_state[r]} for r in roles_in_q}

                roles_to_dec = [r for r in roles_in_q if action_confirmed[r] is None]
                for r in roles_to_dec:

                    to_inc = [arg for arg in self.action_belief_state[r] if arg != action_chosen[r][0]]
                    for arg in to_inc:
                        gd[r][arg] = 1.0 / len(to_inc)

                if debug:
                    print ("update_action_belief_from_confirmation: neg conf distribution: " + str(gd))

                # Update the primary belief distribution by interpolating it with this negative conf distribution.
                for r in gd:
                    for a in gd[r]:
                        self.action_belief_state[r][a] = (self.action_belief_state[r][a] *
                                                          (1 - self.belief_update_rate) +
                                                          gd[r][a] * self.belief_update_rate)
        else:
            print("WARNING: confirmation update string was not yes/no; '" + str(g) + "'")

        if debug:
            print ("update_action_belief_from_groundings: interpolated, new belief distribution: " +
                   str(self.action_belief_state))

        return action_confirmed

    # Given a parse and a list of the roles felicitous in the dialog to update, update those roles' distributions
    # Distribute portion of mass from everything not in confirmations to everything that is evenly.
    def update_action_belief_from_groundings(self, gs, roles):
        debug = False
        if debug:
            print ("update_action_belief_from_groundings called with gs\n" +
                   '\n'.join([str((self.parser.print_parse(g), conf)) for g, conf in gs]) +
                   " and roles " + str(roles))

        # Form belief distribution based only on the incoming groundings.
        gd = {r: {a: 0.0 for a in self.action_belief_state[r]} for r in roles}
        for g, conf in gs:
            if type(g) is bool:
                continue
            if debug:
                print ("update_action_belief_from_groundings processing g:\n" +
                       str((self.parser.print_parse(g), conf)))

            # Crawl parse for recognized actions.
            based_on_action_trees = False
            if 'action' in roles:
                action_trees = self.get_parse_subtrees(g, self.actions)
                if len(action_trees) > 0:
                    if debug:
                        print ("\tupdate_action_belief_from_groundings: action tree update")
                    based_on_action_trees = True
                    portion = conf / float(len(action_trees))
                    for at in action_trees:
                        a = self.parser.ontology.preds[at.idx]
                        gd['action'][a] += portion

                        # Update patient and recipient, if present, with action tree args.
                        # These disregard argument order in favor of finding matching argument types.
                        # This gives us more robustness to bad parses with incorrectly ordered args or incomplete args.
                        if self.parser.ontology.preds[at.idx] != 'move':
                            for r in ['goal', 'patient', 'recipient']:
                                if r in roles and at.children is not None:
                                    for cn in at.children:
                                        if (r in self.action_args[a] and
                                                self.parser.ontology.types[cn.type] in self.action_args[a][r]):
                                            c = self.parser.ontology.preds[cn.idx]
                                            if c not in self.action_belief_state[r]:
                                                continue
                                            gd[r][c] += portion

                        # For 'move', order matters (source versus goal), so handle this separately
                        else:
                            role_order = ['patient', 'source', 'goal']
                            for idx in range(len(at.children)):
                                cn = at.children[idx]
                                r = role_order[idx]
                                if r in roles:  # we might not have asked about each arg
                                    if self.parser.ontology.types[cn.type] in self.action_args[a][r]:
                                        c = self.parser.ontology.preds[cn.idx]
                                        if c not in self.action_belief_state[r]:
                                            continue
                                        gd[r][c] += portion

            # Else, just add counts as appropriate based on roles asked based on a trace of the whole tree.
            # If we were trying to update an action but didn't find any trees, also take this route.
            if not based_on_action_trees:
                if debug:
                        print ("\tupdate_action_belief_from_groundings: crawling update")
                for r in roles:
                    to_traverse = [g]
                    to_increment = []
                    while len(to_traverse) > 0:
                        cn = to_traverse.pop()
                        if self.parser.ontology.types[cn.type] in [t for a in self.actions
                                                                   if r in self.action_args[a]
                                                                   for t in self.action_args[a][r]]:
                            if not cn.is_lambda:  # otherwise utterance isn't grounded
                                c = self.parser.ontology.preds[cn.idx]
                                if c not in self.action_belief_state[r]:
                                    continue
                                to_increment.append(c)
                        if cn.children is not None:
                            to_traverse.extend(cn.children)
                    if len(to_increment) > 0:
                        portion = conf / float(len(to_increment))
                        for c in to_increment:
                            gd[r][c] += portion

            # For roles where no atom received probability mass, put all the mass on 'None'.
            for r in gd:
                if None in gd[r] and sum([gd[r][a] for a in gd[r]]) == 0:
                    gd[r][None] = 1.0

        if debug:
            print ("update_action_belief_from_groundings: groundings distribution: " + str(gd))

        # Update the primary belief distribution by interpolating it with the grounding distribution.
        for r in gd:
            for a in gd[r]:
                self.action_belief_state[r][a] = (self.action_belief_state[r][a] * (1 - self.belief_update_rate) +
                                                  gd[r][a] * self.belief_update_rate)

        if debug:
            print ("update_action_belief_from_groundings: interpolated, new belief distribution: " +
                   str(self.action_belief_state))

    # Given a dictionary of roles to utterances and another of roles to confirmed predicates, build
    # SemanticNodes corresponding to those predicates and to the whole command to match up with entries
    # in the utterance dictionary.
    # us - dictionary mapping roles to utterances
    # rs - dictionary mapping roles to ontological predicates (groundings)
    def induce_utterance_grounding_pairs_from_conversation(self, us, rs):
        debug = False

        conf_surface_forms = set()
        for sfidx in range(len(self.parser.lexicon.surface_forms)):
            for sem_idx in self.parser.lexicon.entries[sfidx]:
                if (len(self.get_parse_subtrees(self.parser.lexicon.semantic_forms[sem_idx], ["yes"])) > 0 or
                        len(self.get_parse_subtrees(self.parser.lexicon.semantic_forms[sem_idx], ["no"])) > 0):
                    conf_surface_forms.add(self.parser.lexicon.surface_forms[sfidx])
        if debug:
            print("conf_surface_forms: " + str(conf_surface_forms))

        pairs = []
        if 'all' in us:  # need to build SemanticNode representing all roles
            if 'all' not in rs:  # build string from rs entries
                sem_str = rs['action']
                if rs['action'] == 'walk':
                    sem_str += '(' + rs['goal'] + ')'
                elif rs['action'] == 'bring':
                    sem_str += '(' + rs['patient'] + ',' + rs['recipient'] + ')'
                else:  # ie. 'move'
                    sem_str += '(' + rs['patient'] + ',' + rs['source'] + ',' + rs['goal'] + ')'
            else:  # else, string is being provided but entries aren't, probably
                sem_str = rs['all']
            cat_idx = self.parser.lexicon.read_category_from_str('M')  # a command
            grounded_form = self.parser.lexicon.read_semantic_form_from_str(sem_str, cat_idx, None, [])
            for u in us['all']:
                if [u, grounded_form] not in pairs and len(set(self.parser.tokenize(u)) & conf_surface_forms) == 0:
                    pairs.append([u, grounded_form])
            if debug:
                print ("induce_utterance_grounding_pairs_from_conversation: adding 'all' pairs for gr form " +
                       self.parser.print_parse(grounded_form) + " for utterances: " + ' ; '.join(us['all']))

        for r in [_r for _r in self.roles if _r in us and rs[_r] is not None]:
            if r == 'action':
                # TODO: Seems like we should do something here but it's actually not clear to me what a grounding
                # TODO: for an action word by itself looks like. The syntax around them, like, matters.
                # TODO: These might have to be learned primarily through the overall restatement, in which case
                # TODO: we should disallow it as the role_asked and default to full restate when the least
                # TODO: confident role comes out as 'action'.
                pass

            else:
                cat_idx = self.parser.lexicon.read_category_from_str('NP')  # patients and recipients always NP alone
                grounded_form = self.parser.lexicon.read_semantic_form_from_str(rs[r], cat_idx, None, [])

                for u in us[r]:
                    if len(u) > 0 and [u, grounded_form] not in pairs and len(set(self.parser.tokenize(u)) & conf_surface_forms) == 0:
                        pairs.append([u, grounded_form])
                if debug and len(us[r]) > 0:
                    print ("induce_utterance_grounding_pairs_from_conversation: adding '" + r + "' pairs for gr form " +
                           self.parser.print_parse(grounded_form) + " for utterances: " + ' ; '.join(us[r]))

        return pairs

    # Parse and ground a given utterance.
    def parse_and_ground_utterance(self, u):
        debug = False

        # TODO: do probabilistic updates by normalizing the parser outputs in a beam instead of only considering top-1
        # TODO: confidence could be propagated through the confidence values returned by the grounder, such that
        # TODO: this function returns tuples of (grounded parse, parser conf * grounder conf)
        parse_generator = self.parser.most_likely_cky_parse(u, reranker_beam=self.parse_beam, timeout=self.budget_for_parsing)
        cgtr = next(parse_generator)
        if self.parser.parsing_timeout_on_last_parse:
            self.parser_timeouts += 1
        p = None
        if cgtr is not None and cgtr[0] is not None:
            p = cgtr[0]  # most_likely_cky_parse returns a 4-tuple, the first of which is the parsenode
            if debug:
                print("parse_and_ground_utterance: parsed '" + u + "' to " + self.parser.print_parse(p.node))

            # Get semantic trees with hanging lambdas instantiated.
            gn = self.ground_semantic_form(p.node)

        else:
            if debug:
                print("parse_and_ground_utterance: could not generate a parse for the utterance")
            gn = []

        return gn, p

    # Ground semantic form.
    def ground_semantic_form(self, s):
        debug = False

        gs = self.call_function_with_timeout(self.grounder.ground_semantic_tree, {"root": s},
                                             self.budget_for_parsing)
        if gs is not None:
            # normalize grounding confidences such that they sum to one and return pairs of grounding, conf
            gn = self.sort_groundings_by_conf(gs)
            if debug:
                print ("ground_semantic_form: resulting groundings with normalized confidences: " +
                       "\n\t" + "\n\t".join([" ".join([str(t) if type(t) is bool else self.parser.print_parse(t),
                                                       str(c)])
                                            for t, c in gn]))
        else:
            gn = []
            if debug:
                print("ground_semantic_form: grounding timeout for " + self.parser.print_parse(s))
            self.grounder_timeouts += 1

        return gn

    # Given a set of groundings, return them and their confidences in sorted order.
    def sort_groundings_by_conf(self, gs):
        s = sum([c for _, _, c in gs])
        gn = [(t, c / s if s > 0 else c / float(len(gs))) for t, _, c in gs]
        return sorted(gn, key=lambda x: x[1], reverse=True)

    # Given a parse and a list of predicates, return the subtrees in the parse rooted at those predicates.
    # If a subtree is rooted beneath one of the specified predicates, it will not be returned (top-level only).
    def get_parse_subtrees(self, root, preds):
        debug = False
        if debug:
            print ("get_parse_subtrees called for root " + self.parser.print_parse(root) +
                   " and preds " + str(preds))

        trees_found = []
        pred_idxs = [self.parser.ontology.preds.index(p) for p in preds]
        if root.idx in pred_idxs:
            trees_found.append(root)
        elif root.children is not None:
            for c in root.children:
                trees_found.extend(self.get_parse_subtrees(c, preds))
        if debug:
            print("get_parse_subtrees: found trees " + str(trees_found))
        return trees_found

    # Returns a list of all the ontological predicates/atoms in the given tree, stripping structure.
    # Returns these predicates as strings.
    def scrape_preds_from_parse(self, root):
        preds_found = []
        if root.idx is not None:
            preds_found.append(self.parser.ontology.preds[root.idx])
        if root.children is not None:
            for c in root.children:
                preds_found.extend(self.scrape_preds_from_parse(c))
        return preds_found

    # Sample a discrete action from the current belief counts.
    # Each argument of the discrete action is a tuple of (argument, confidence) for confidence in [0, 1].
    def sample_action_from_belief(self, current_confirmed, arg_max=False):
        debug = False
        if debug:
            print ("sample_action_from_belief: sampling from belief " + str(self.action_belief_state) +
                   " with current_confirmed=" + str(current_confirmed) + " and arg_max=" + str(arg_max))

        chosen = {r: (None, 0) if current_confirmed[r] is None else (current_confirmed[r], 1.0)
                  for r in self.roles}
        for r in [_r for _r in self.roles if current_confirmed[_r] is None]:

            valid_entries = [entry for entry in self.action_belief_state[r]]
            dist = [self.action_belief_state[r][entry] for entry in valid_entries]
            s = sum(dist)
            # this normalization shouldn't be necessary but may ensure we get a sum to 1.0 so numpy doesn't crash
            dist = [dist[idx] / s for idx in range(len(dist))]
            if debug:
                print ("sample_action_from_belief: role '" + r + "' valid entries: " + str(valid_entries) +
                       ", dist: " + str(dist))
            if arg_max:
                max_idxs = [idx for idx in range(len(dist)) if dist[idx] == max(dist)]
                c = np.random.choice([valid_entries[idx] for idx in max_idxs], 1)
                if debug:
                    print ("sample_action_from_belief: ... max_idxs: " + str(max_idxs) + ", c " + str(c))
            else:
                c = np.random.choice([valid_entries[idx]
                                      for idx in range(len(valid_entries))],
                                     1, p=dist)
            chosen[r] = (c[0], dist[valid_entries.index(c[0])])

        if debug:
            print ("sample_action_from_belief: sampled chosen=" + str(chosen))

        return chosen

    # Return a string question based on a discrete sampled action.
    def get_question_from_sampled_action(self, sampled_action, include_threshold):
        debug = False
        if debug:
            print("get_question_from_sampled_action called with " + str(sampled_action) + ", " + str(include_threshold))

        # Include roles in the question if they exceed the specified confidence threshold or a
        # uniform sample drawn in [0, 1] is less than the confidence in the role (which is also in [0, 1])
        # Don't sample 'action'; that needs to be above inclusion threshold (with threshold 1.0, it needs
        # to be explicitly confirmed.)
        roles_to_include = [r for r in self.roles if
                            (sampled_action[r][1] >= include_threshold or
                             (r != 'action' and sampled_action[r][1] > np.random.random(1)[0])) and
                            sampled_action[r][0] is not None]  # can't be confident to include absence
        if 'action' in roles_to_include:
            relevant_roles = ['action'] + [r for r in (self.action_args[sampled_action['action'][0]].keys()
                                           if sampled_action['action'][0] is not None else
                                                       ['patient', 'recipient', 'source', 'goal'])]
        else:
            relevant_roles = self.roles[:]
        roles_to_include = [r for r in roles_to_include
                            if r in relevant_roles and r not in self.no_clarify]  # strip recipient from 'bring' etc.
        confidences = {r: sampled_action[r][1] for r in relevant_roles}
        s_conf = sorted(confidences.items(), key=operator.itemgetter(1))
        if debug:
            print("get_question_from_sampled_action: s_conf " + str(s_conf))

        # Determine which args to include as already understood in question and which arg to focus on.
        if 'action' in roles_to_include:
            least_conf_role = s_conf[0][0]
        else:
            least_conf_role = 'action'  # need to get action confirmed first
        if max([conf for _, conf in s_conf]) == 0.0:  # no confidence
            least_conf_role = None
        if debug:
            print ("get_question_from_sampled_action: roles_to_include " + str(roles_to_include) +
                   " with least_conf_role " + str(least_conf_role))

        # No useful question can be formed.
        if least_conf_role is not None and sampled_action[least_conf_role][0] is None and len(roles_to_include) == 0:
            q = "Please rephrase your original request."
            return q, None, roles_to_include, []

        # Ask a question.
        roles_in_q = []  # different depending on action selection
        if roles_to_include == self.roles:  # all roles are above threshold, so perform.
            if sampled_action['action'][0] == 'walk':
                q = "You want me to go to <g>here</g> (not manipulate any objects)?"
                roles_in_q.extend(['action', 'goal'])
            elif sampled_action['action'][0] == 'bring':
                q = "You want me to deliver <p>this</p> to <r>this person</r>?"
                roles_in_q.extend(['action', 'patient', 'recipient'])
            else:  # eg. move
                q = "You want me to move <p>this</p> from <s>here</s> to <g>there</g>?"
                roles_in_q.extend(['action', 'patient', 'source', 'goal'])

        elif least_conf_role == 'action':  # ask for action confirmation
            if sampled_action['action'][0] is None:  # need to clarify what the action is
                args = []
                for r in [_r for _r in self.roles if _r != 'action']:
                    if r in roles_to_include:
                        if r == 'patient':
                            args.append("<p>this</p>")
                        elif r == 'recipient':
                            args.append("<r>this person</r>")
                        elif r == 'source':
                            args.append("<s>here</s>")
                        elif r == 'goal':
                            args.append("<g>here</g>")
                        roles_in_q.append(r)
                if len(args) > 2:
                    q = "What should I do involving " + ', '.join(args[:-1]) + ", and " + args[-1] + "?"
                elif len(args) == 2:
                    q = "What should I do involving " + args[0] + " and " + args[1] + "?"
                elif len(args) == 1:
                    q = "What should I do involving " + args[0] + "?"
                else:
                    q = "What kind of action should I perform?"
            elif sampled_action['action'][0] == 'walk':
                if 'goal' in roles_to_include:
                    q = "You want me to go to <g>here</g> (not manipulate any objects)?"
                    roles_in_q.extend(['action', 'goal'])
                else:
                    q = "You want me to go somewhere? (not manipulate any objects)"
                    roles_in_q.extend(['action'])
            elif sampled_action['action'][0] == 'bring':
                if 'patient' in roles_to_include:
                    if 'recipient' in roles_to_include:
                        q = "You want me to deliver <p>this</p> to <r>this person</r>?"
                        roles_in_q.extend(['action', 'patient', 'recipient'])
                    else:
                        q = "You want me to deliver <p>this</p> to someone?"
                        roles_in_q.extend(['action', 'patient'])
                elif 'recipient' in roles_to_include:
                    q = "You want me to deliver something to <r>this person</r>?"
                    roles_in_q.extend(['action', 'recipient'])
                else:
                    q = "You want me to deliver something for someone?"
                    roles_in_q.extend(['action'])
            else:  # eg. 'move'
                roles_in_q.append('action')
                if 'patient' in roles_to_include:
                    q = "You want me to move <p>this</p>"
                    roles_in_q.append('patient')
                else:
                    q = "You want me to move an item"
                if 'source' in roles_to_include:
                    q += " from <s>here</s>"
                    roles_in_q.append('source')
                else:
                    q += " from somewhere"
                if 'goal' in roles_to_include:
                    q += " to <g>there</g>"
                    roles_in_q.append('goal')
                else:
                    q += " to somewhere"
                q += " (not give it to someone)"
                q += "?"

        elif least_conf_role == 'patient':  # ask for patient confirmation
            if sampled_action['patient'][0] is None:
                if 'action' in roles_to_include:
                    if sampled_action['action'][0] == 'bring':
                        if 'recipient' in roles_to_include:
                            q = "What should I deliver to <r>this person</r>?"
                            roles_in_q.extend(['action', 'recipient'])
                        else:  # i.e. bring with no recipient
                            q = "What should I find to deliver?"
                            roles_in_q.extend(['action'])
                    else:  # ie. 'move'
                        q = "What should I move"
                        roles_in_q.append('action')
                        if 'source' in roles_to_include:
                            q += " from <s>here</s>"
                            roles_in_q.append('source')
                        if 'goal' in roles_to_include:
                            q += " to <g>there</g>"
                            roles_in_q.append('goal')
                        q += "?"
                else:
                    args = []
                    for r in [_r for _r in self.roles if _r != 'action']:
                        if r in roles_to_include:
                            if r == 'patient':
                                args.append("<p>this</p>")
                            elif r == 'recipient':
                                args.append("<r>this person</r>")
                            elif r == 'source':
                                args.append("<s>here</s>")
                            elif r == 'goal':
                                args.append("<g>here</g>")
                            roles_in_q.append(r)
                    if len(args) > 2:
                        q = ("What is involved in what I should do besides " +
                             ', '.join(args[:-1]) + ", and " + args[-1] + "?")
                    elif len(args) == 2:
                        q = "What is involved in what I should do besides " + args[0] + " and " + args[1] + "?"
                    elif len(args) == 1:
                        q = "What is involved in what I should do besides " + args[0] + "?"
                    else:
                        q = "What is involved in what I should do?"
            else:
                if 'action' in roles_to_include:
                    if sampled_action['action'][0] == 'bring':
                        if 'recipient' in roles_to_include:
                            q = "You want me to deliver <p>this</p> to <r>this person</r>?"
                            roles_in_q.extend(['action', 'patient', 'recipient'])
                        else:
                            q = "You want me to deliver <p>this</p> to someone?"
                            roles_in_q.extend(['action', 'patient'])
                    else:  # ie. 'move'
                        q = "You want me to move <p>this</p>"
                        roles_in_q.extend(['action', 'patient'])
                        if 'source' in roles_to_include:
                            q += " from <s>here</s>"
                            roles_in_q.append('source')
                        else:
                            q += " from somewhere"
                        if 'goal' in roles_to_include:
                            q += " to <g>there</g>"
                            roles_in_q.append('goal')
                        else:
                            q += " to somewhere"
                        q += " (not give it to someone)"
                        q += "?"
                else:
                    args = []
                    for r in [_r for _r in self.roles if _r != 'action']:
                        if r in roles_to_include:
                            if r == 'patient':
                                args.append("<p>this</p>")
                            elif r == 'recipient':
                                args.append("<r>this person</r>")
                            elif r == 'source':
                                args.append("<s>here</s>")
                            elif r == 'goal':
                                args.append("<g>here</g>")
                            roles_in_q.append(r)
                    if len(args) > 2:
                        q = ("You want me to do something involving " +
                             ', '.join(args[:-1]) + ", and " + args[-1] + "?")
                    elif len(args) == 2:
                        q = "You want me to do something involving " + args[0] + " and " + args[1] + "?"
                    elif len(args) == 1:
                        q = "You want me to do something involving " + args[0] + "?"
                    else:
                        q = "What is involved in what I should do?"

        elif least_conf_role == 'recipient':  # ask for recipient confirmation
            if sampled_action['recipient'][0] is None:
                if 'action' in roles_to_include:
                    if sampled_action['action'][0] == 'walk':
                        raise ValueError("ERROR: get_question_from_sampled_action got a sampled action " +
                                         "with empty recipient ask in spite of action being walk")
                    elif 'patient' in roles_to_include:
                        q = "To whom should I deliver <p>this</p>?"
                        roles_in_q.extend(['action', 'patient'])
                    else:  # i.e. bring with no recipient
                        q = "Who should receive what I deliver?"
                        roles_in_q.extend(['action'])
                else:
                    if 'patient' in roles_to_include:
                        q = "Who is involved in what I should do with <p>this</p>?"
                        roles_in_q.extend(['patient'])
                    else:
                        q = "Who is involved in what I should do?"
            else:
                if 'action' in roles_to_include:
                    if 'patient' in roles_to_include:
                        q = "You want me to deliver <p>this</p> to <r>this person</r>?"
                        roles_in_q.extend(['action', 'patient', 'recipient'])
                    else:
                        q = "You want me to deliver something to <r>this person</r>?"
                        roles_in_q.extend(['action', 'recipient'])
                elif 'patient' in roles_to_include:
                    q = "You want me to do something with <p>this</p> for <r>this person</r>?"
                    roles_in_q.extend(['patient', 'recipient'])
                else:
                    q = "You want me to do something for <r>this person</r>?"
                    roles_in_q.extend(['recipient'])

        elif least_conf_role == 'source':  # ask for source confirmation
            if 'action' in roles_to_include:
                if sampled_action['action'][0] != 'move':
                    raise ValueError("ERROR: get_question_from_sampled_action got a sampled action " +
                                     "for '" + sampled_action['action'][0] + "' with infelicitous " +
                                     "least confident role 'source'")
                if 'patient' in roles_to_include:
                    q = "<p>this</p>"
                    roles_in_q.append('patient')
                else:
                    q = "something"
                if sampled_action['source'][0] is None:
                    q = "Where should I move " + q + " from on its way"
                else:
                    q = "I should move " + q + " from <s>here</s>"
                    roles_in_q.append('source')
                roles_in_q.append('action')
                if 'goal' in roles_to_include:
                    q += " to <g>there</g>"
                    roles_in_q.append('goal')
                else:
                    q += " somewhere else"
                q += "?"
            else:
                args = []
                for r in [_r for _r in self.roles if _r != 'action']:
                    if r in roles_to_include:
                        if r == 'patient':
                            args.append("<p>this</p>")
                        elif r == 'recipient':
                            args.append("<r>this person</r>")
                        elif r == 'source':
                            args.append("<s>here</s>")
                        elif r == 'goal':
                            args.append("<g>here</g>")
                        roles_in_q.append(r)
                if len(args) > 2:
                    q = ("What is the first place involved regarding " +
                         ', '.join(args[:-1]) + ", and " + args[-1] + "?")
                elif len(args) == 2:
                    q = "What is the first place involved regarding " + args[0] + " and " + args[1] + "?"
                elif len(args) == 1:
                    q = "What is the first place involved regarding " + args[0] + "?"
                else:
                    q = "What is the first place involved in what I should do?"

        elif least_conf_role == 'goal':  # ask for goal confirmation
            if 'action' in roles_to_include:
                if sampled_action['action'][0] == 'walk':
                    if 'goal' in roles_to_include:
                        q = "You want me to go to <g>here</g> (not manipulate any objects)?"
                        roles_in_q.extend(['action', 'goal'])
                    else:
                        q = "Where should I go?"
                        roles_in_q.extend(['action'])
                else:  # ie. move
                    if 'patient' in roles_to_include:
                        q = "<p>this</p>"
                        roles_in_q.append('patient')
                    else:
                        q = "something"
                    if 'source' in roles_to_include:
                        q += " from <s>here</s>"
                        roles_in_q.append('source')
                    else:
                        q += " from somewhere"
                    if sampled_action['goal'][0] is None:
                        q = "To where should I move " + q
                    else:
                        q = "I should move " + q + " to <g>there</g>"
                        roles_in_q.append('goal')
                    roles_in_q.append('action')
                    q += "?"
            else:
                args = []
                for r in [_r for _r in self.roles if _r != 'action']:
                    if r in roles_to_include:
                        if r == 'patient':
                            args.append("<p>this</p>")
                        elif r == 'recipient':
                            args.append("<r>this person</r>")
                        elif r == 'source':
                            args.append("<s>here</s>")
                        elif r == 'goal':
                            args.append("<g>here</g>")
                        roles_in_q.append(r)
                if len(args) > 2:
                    q = ("What is the second place involved regarding " +
                         ', '.join(args[:-1]) + ", and " + args[-1] + "?")
                elif len(args) == 2:
                    q = "What is the second place involved regarding " + args[0] + " and " + args[1] + "?"
                elif len(args) == 1:
                    q = "What is the second place involved regarding " + args[0] + "?"
                else:
                    q = "What is the second place involved in what I should do?"
        else:  # least_conf_role is None, i.e. no confidence in any arg, so ask for full restatement
            q = "Please rephrase your original request."

        if debug:
            print ("get_question_from_sampled_action: returning q='" + q + "', least_conf_role=" +
                   str(least_conf_role) + ", roles_to_include=" + str(roles_to_include) + ", and roles_in_q="
                   + str(roles_in_q))

        # Return the question and the roles included in it.
        # If the user affirms, all roles included in the question should have confidence boosted to 1.0
        # If the user denies, all roles included in the question should have their counts subtracted.
        return q, least_conf_role, roles_to_include, roles_in_q

    # Given the current set of utterance/grounding pairs, return pairs of utterance/semantics
    # based on parsing in beams and searching for parses that yield correct grounding.
    def get_semantic_forms_for_induced_pairs(self, parse_reranker_beam, interpolation_reranker_beam, verbose=0,
                                             use_condor=False, condor_target_dir=None, condor_script_dir=None):

        if use_condor:
            agent_fn = os.path.join(condor_target_dir, "temp.agent.pickle")
            with open(agent_fn, 'wb') as f:
                pickle.dump(self, f)
            pairs_in_fn = os.path.join(condor_target_dir, "temp.gpairs.in.pickle")
            with open(pairs_in_fn, 'wb') as f:
                pickle.dump(self.induced_utterance_grounding_pairs, f)
            pairs_out_fn = os.path.join(condor_target_dir, "temp.gpairs.out.pickle")
            script_fn = os.path.join(condor_script_dir, "_condor_get_utt_sem_pairs.py")
            cmd = ("python3 " + script_fn +
                   " --target_dir " + condor_target_dir +
                   " --script_dir " + condor_script_dir +
                   " --agent_infile " + agent_fn +
                   " --parse_reranker_beam " + str(parse_reranker_beam) +
                   " --interpolation_reranker_beam " + str(interpolation_reranker_beam) +
                   " --pairs_infile " + pairs_in_fn +
                   " --outfile " + pairs_out_fn)
            err = os.system(cmd)  # blocking call to script that launches jobs and collects them map-reduce style
            print("_condor_get_training_pairs output: " + str(err))
            with open(pairs_out_fn, 'rb') as f:
                raw_pairs = pickle.load(f)
            os.system("rm " + agent_fn)
            os.system("rm " + pairs_in_fn)
            os.system("rm " + pairs_out_fn)

            # Since we distributed the computation, we need to update the local Ontology with any new types
            # that were introduced by weird 'and' rules in the pairs.
            # We do this by getting sem forms as strings, so we need to read them in afresh now.
            utterance_semantic_pairs = []
            for s, sem_str, g in raw_pairs:
                ccg_str, form_str = sem_str.split(" : ")
                ccg = self.parser.lexicon.read_category_from_str(ccg_str)
                form = self.parser.lexicon.read_semantic_form_from_str(form_str, None, None, [])
                form.category = ccg
                utterance_semantic_pairs.append([s, form, g])

        else:

            # Induce utterance/semantic form pairs from utterance/grounding pairs.
            utterance_semantic_pairs = []
            for [x, g] in self.induced_utterance_grounding_pairs:
                if verbose > 0:
                    print ("get_semantic_forms_for_induced_pairs: looking for semantic forms for x '" + str(x) +
                           "' with grounding " + self.parser.print_parse(g))

                parses = []
                # no timeouts during induction/training; allow parser to wear itself out looking for solutions
                cky_parse_generator = self.parser.most_likely_cky_parse(x, reranker_beam=parse_reranker_beam,
                                                                        debug=False, timeout=None)
                cgtr = next(cky_parse_generator)
                parse = None
                if cgtr is not None:
                    parse = cgtr[0]
                    score = cgtr[1]  # most_likely_cky_parse returns a 4-tuple headed by the parsenode and score
                latent_forms_considered = 1
                while (parse is not None and len(parses) < interpolation_reranker_beam and
                       latent_forms_considered < self.latent_forms_to_consider_for_induction):

                    if verbose > 2:
                        print ("get_semantic_forms_for_induced_pairs: ... grounding semantic form " +
                               self.parser.print_parse(parse.node, True) + " with scores p " + str(score))
                    # Allow grounder to run indefinitely at training time.
                    gs = self.grounder.ground_semantic_tree(parse.node)
                    if gs is not None:
                        gn = self.sort_groundings_by_conf(gs)
                    else:
                        gn = []
                    if len(gn) > 0:
                        for gz, g_score in gn:
                            print ("get_semantic_forms_for_induced_pairs: ...... form grounded to " +
                                   str(self.parser.print_parse(gz) if type(gz) is not bool else str(gz)) +
                                   " with score " + str(g_score))
                            if ((type(gz) is bool and gz == g) or
                                    (type(gz) is not bool and g.equal_allowing_commutativity(gz, self.parser.ontology))):
                                parses.append([parse, score + math.log(g_score + 1.0)])  # add 1 for zero probabilities
                                print ("get_semantic_forms_for_induced_pairs: ... found semantic form " +
                                       self.parser.print_parse(parse.node, True) +
                                       " with scores p " + str(score) + ", g " + str(g_score))
                                break

                    cgtr = next(cky_parse_generator)
                    parse = None
                    if cgtr is not None:
                        parse = cgtr[0]
                        score = cgtr[1]

                    latent_forms_considered += 1

                if len(parses) > 0:
                    sorted_interpolation = sorted(parses, key=lambda t: t[1], reverse=True)
                    best_interpolated_parses = [parse for parse, score in sorted_interpolation
                                                if np.isclose(score, sorted_interpolation[0][1])]
                    best_interpolated_parse = random.choice(best_interpolated_parses)
                    utterance_semantic_pairs.append([x, best_interpolated_parse.node, g])
                    print("... re-ranked to choose " + self.parser.print_parse(best_interpolated_parse.node))
                    best_interpolated_parse.node.commutative_lower_node(self.parser.ontology)
                    print("... commutative lowered to " + self.parser.print_parse(best_interpolated_parse.node))
                elif len(self.parser.tokenize(x)) <= self.parser.max_multiword_expression:
                    # Find the categories of entries in lexicon, if any, matching g.
                    matching_categories = []
                    for surface_idx in range(len(self.parser.lexicon.surface_forms)):
                        for sem_idx in self.parser.lexicon.entries[surface_idx]:
                            if g.equal_allowing_commutativity(self.parser.lexicon.semantic_forms[sem_idx],
                                                              self.parser.ontology, ignore_syntax=True):
                                matching_categories.append(self.parser.lexicon.semantic_forms[sem_idx].category)
                    if len(matching_categories) > 0:
                        utterance_semantic_pairs = []
                        for c in matching_categories:
                            print ("get_semantic_forms_for_induced_pairs: no semantic parse found; adding " +
                                   "possible synonymy pair " + "'" + str(x) + "' with " +
                                   self.parser.lexicon.compose_str_from_category(c) + " : " +
                                   self.parser.print_parse(g))
                            parse = copy.deepcopy(g)
                            parse.category = c
                            utterance_semantic_pairs.append([x, parse, g])
                elif verbose > 0:
                    print ("get_semantic_forms_for_induced_pairs: no semantic parse found matching " +
                           "grounding for pair '" + str(x) + "', " + self.parser.print_parse(g))

        return utterance_semantic_pairs

    def call_function_with_timeout(self, f, args, t):
        if t is not None:
            signal.signal(signal.SIGALRM, self.timeout_signal_handler)
            signal.alarm(t)
            try:
                r = f(**args)
            except RuntimeError:
                r = None
            signal.alarm(0)
        else:
            r = f(**args)
        return r

    def timeout_signal_handler(self, signum, frame):
        raise RuntimeError()

