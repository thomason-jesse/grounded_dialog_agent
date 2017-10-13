#!/usr/bin/env python
__author__ = 'jesse'

import math
import numpy as np
import operator


class Agent:

    # Takes an instantiated, trained parser, a knowledge base grounder, and an input/output instance.
    def __init__(self, parser, grounder, io):
        self.parser = parser
        self.grounder = grounder
        self.io = io

        # hyperparameters
        self.parse_beam = 1
        self.threshold_to_accept_role = 0.9

        # static information about expected actions and their arguments
        self.roles = ['action', 'patient', 'recipient']
        self.actions = ['walk', 'bring']
        self.action_args = {'walk': {'patient': ['l']},
                            'bring': {'patient': ['i'], 'recipient': ['p']}}  # expected argument types per action

        self.action_belief_state = None  # maintained during action dialogs to track action, patient, recipient
        # pairs of [utterance, grounded SemanticNode] induced from conversations
        self.induced_utterance_grounding_pairs = []

    # Start a new action dialog from utterance u given by a user.
    # Clarifies the arguments of u until the action is confirmed by the user.
    def start_action_dialog(self, u):
        debug = True

        # Start with a count of 1.0 on each role being empty (of which only recipient can remain empty in the end).
        # As more open-ended and yes/no utterances are parsed, these counts will be updated to reflect the roles
        # we are trying to fill. Action beliefs are sampled from probability distributions induced from these counts.
        self.action_belief_state = {'action': {a: 1.0 for a in self.actions},
                                    'patient': {p: 1.0 for p in self.parser.ontology.preds
                                                if (self.parser.ontology.types[self.parser.ontology.entries[
                                                        self.parser.ontology.preds.index(p)]] in
                                                    self.action_args['walk']['patient'] or
                                                    self.parser.ontology.types[self.parser.ontology.entries[
                                                        self.parser.ontology.preds.index(p)]] in
                                                    self.action_args['bring']['patient'])},
                                    'recipient': {r: 1.0 for r in self.parser.ontology.preds
                                                  if self.parser.ontology.types[self.parser.ontology.entries[
                                                      self.parser.ontology.preds.index(r)]] in
                                                  self.action_args['bring']['recipient']}}
        for r in ['patient', 'recipient']:  # questions currently support None action, but I think it's weird maybe
            self.action_belief_state[r][None] = 1.0
        if debug:
            print ("start_action_dialog starting with u '" + str(u) + "' and action belief state: "
                   + str(self.action_belief_state))

        user_utterances_by_role = {r: [] for r in self.roles + ['all']}
        user_utterances_by_role['all'].append(u)

        # Run the parser and grounder on the utterance
        gps = self.parse_and_ground_utterance(u)

        # Update the belief state based on the utterance.
        for gp, conf in gps:
            # conf scores sum to 1 based on parse_and_ground_utterance behavior.
            self.update_action_belief_from_grounding(gp, self.roles, count=conf)

        # Ask a follow up question based on the new belief state.
        # This continues until an action is chosen.
        action_confirmed = {r: None for r in self.roles}
        while (action_confirmed['action'] is None or action_confirmed['patient'] is None or
                (action_confirmed['action'] == 'bring' and action_confirmed['recipient'] is None)):

            # Sample a chosen action from the current belief counts.
            # If arg_max, gets current highest-confidence belief. Else, creates confidence distribution and samples.
            action_chosen = self.sample_action_from_belief(action_confirmed, arg_max=True)

            # Determine what question to ask based on missing arguments in chosen action.
            q, role_asked, roles_conf, roles_in_q = self.get_question_from_sampled_action(action_chosen,
                                                                                          self.threshold_to_accept_role)

            # Ask question and get user response.
            self.io.say_to_user(q)
            ur = self.io.get_from_user()

            # Update action belief based on user response.
            gprs = self.parse_and_ground_utterance(ur)
            if role_asked is None:  # asked to repeat whole thing
                user_utterances_by_role['all'].append(ur)
                for gpr, conf in gprs:
                    # conf scores across gprs will sum to 1 based on parse_and_ground_utterance behavior.
                    self.update_action_belief_from_grounding(gpr, self.roles, count=conf)
            elif action_chosen[role_asked][0] is None:  # asked an open-ended question for a particular role
                user_utterances_by_role[role_asked].append(ur)
                for gpr, conf in gprs:
                    self.update_action_belief_from_grounding(gpr, [role_asked], count=conf)
            else:  # asked a yes/no question confirming one or more roles
                for gpr, conf in gprs:
                    self.update_action_belief_from_confirmation(gpr, action_confirmed, action_chosen,
                                                                roles_in_q, count=conf)

            if debug:
                print "start_action_dialog: updated action belief state: " + str(self.action_belief_state)

        # Induce utterance/grounding pairs from this conversation.
        new_i_pairs = self.induce_utterance_grounding_pairs_from_conversation(user_utterances_by_role,
                                                                              action_confirmed)
        self.induced_utterance_grounding_pairs.extend(new_i_pairs)

        # Perform the chosen action.
        self.io.perform_action(action_confirmed['action'], action_confirmed['patient'],
                               action_confirmed['recipient'])

    def update_action_belief_from_confirmation(self, g, action_confirmed, action_chosen, roles_in_q, count=1.0):
        debug = True

        if debug:
            print "update_action_belief_from_confirmation: confirmation response parse " + self.parser.print_parse(g)
        if g.type == self.parser.ontology.types.index('c'):
            if g.idx == self.parser.ontology.preds.index('yes'):
                for r in roles_in_q:
                    action_confirmed[r] = action_chosen[r][0]
                    if debug:
                        print ("update_action_belief_from_confirmation: confirmed role " + r + " with argument " +
                               action_chosen[r][0])
            elif g.idx == self.parser.ontology.preds.index('no'):
                if len(roles_in_q) > 0:

                    # Find the second-closest count among the roles to establish an amount by which to decrement
                    # the whole set to ensure at least one argument is no longer maximal.
                    min_diff = None
                    for r in roles_in_q:
                        second = max([self.action_belief_state[r][c] for c in self.action_belief_state[r]
                                      if c != action_chosen[r][0]])
                        diff = self.action_belief_state[r][action_chosen[r][0]] - second
                        if diff < min_diff or min_diff is None:
                            min_diff = diff

                    inc = min_diff + count / float(len(roles_in_q))  # add hinge of count distributed over roles
                    for r in roles_in_q:
                        self.action_belief_state[r][action_chosen[r][0]] -= inc
                        if debug:
                            print ("update_action_belief_from_confirmation: subtracting from " + r + " " +
                                   action_chosen[r][0] + "; " + str(inc))
        else:
            # TODO: could add a loop here to force expected response type; create feedback for
            # TODO: getting synonyms for yes/no maybe
            print "WARNING: grounding for confirmation did not produce yes/no"

    # Given a dictionary of roles to utterances and another of roles to confirmed predicates, build
    # SemanticNodes corresponding to those predicates and to the whole command to match up with entries
    # in the utterance dictionary.
    def induce_utterance_grounding_pairs_from_conversation(self, us, rs):
        debug = True

        pairs = []
        if 'all' in us:  # need to build SemanticNode representing all roles
            sem_str = rs['action']
            if rs['action'] == 'walk':
                sem_str += '(' + rs['patient'] + ')'
            else:  # i.e. 'bring'
                sem_str += '(' + rs['patient'] + ',' + rs['recipient'] + ')'
            cat_idx = self.parser.lexicon.read_category_from_str('M')  # a command
            grounded_form = self.parser.lexicon.read_semantic_form_from_str(sem_str, cat_idx,
                                                                            None, [], False)
            for u in us['all']:
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
                grounded_form = self.parser.lexicon.read_semantic_form_from_str(rs[r], cat_idx,
                                                                                None, [], False)

                for u in us[r]:
                    pairs.append([u, grounded_form])
                if debug and len(us[r]) > 0:
                    print ("induce_utterance_grounding_pairs_from_conversation: adding '" + r + "' pairs for gr form " +
                           self.parser.print_parse(grounded_form) + " for utterances: " + ' ; '.join(us[r]))

        return pairs

    # Parse and ground a given utterance.
    def parse_and_ground_utterance(self, u):
        debug = True

        # TODO: do probabilistic updates by normalizing the parser outputs in a beam instead of only considering top-1
        # TODO: confidence could be propagated through the confidence values returned by the grounder, such that
        # TODO: this function returns tuples of (grounded parse, parser conf * grounder conf)
        parse_generator = self.parser.most_likely_cky_parse(u, reranker_beam=self.parse_beam)
        p, _, _, _ = next(parse_generator)
        if p is not None:
            if debug:
                print "parse_and_ground_utterance: parsed '" + u + "' to " + self.parser.print_parse(p.node)

            # Get semantic trees with hanging lambdas instantiated.
            gs = self.grounder.ground_semantic_tree(p.node)

            # normalize grounding confidences such that they sum to one and return pairs of grounding, conf
            gn = self.sort_groundings_by_conf(gs)

            if debug:
                print ("parse_and_ground_utterance: resulting groundings with normalized confidences " +
                       "\n\t" + "\n\t".join([" ".join([str(t) if type(t) is bool else self.parser.print_parse(t),
                                                       str(c)])
                                            for t, c in gn]))
        else:
            if debug:
                print "parse_and_ground_utterance: could not generate a parse for the utterance"
            gn = []

        return gn

    # Given a set of groundings, return them and their confidences in sorted order.
    def sort_groundings_by_conf(self, gs):
        s = sum([c for _, _, c in gs])
        gn = [(t, c / s if s > 0 else c / float(len(gs))) for t, _, c in gs]
        return sorted(gn, key=lambda x: x[1], reverse=True)

    # Given a parse and a list of the roles felicitous in the dialog to update, update those roles' distributions
    # Increase count of possible slot files for each role that appear in the groundings, and decay those that
    # appear in no groundings.
    def update_action_belief_from_grounding(self, g, roles, count=1.0):
        debug = True
        if debug:
            print ("update_action_belief_from_grounding called with g " + self.parser.print_parse(g) +
                   " and roles " + str(roles))

        # Track which slot-fills appear for each role so we can decay everything but then after updating counts
        # positively.
        role_candidates_seen = {r: set() for r in roles}

        # Crawl parse for recognized actions.
        if 'action' in roles:
            action_trees = self.get_parse_subtrees(g, self.actions)
            if len(action_trees) > 0:
                inc = count / float(len(action_trees))
                for at in action_trees:
                    a = self.parser.ontology.preds[at.idx]
                    if a not in self.action_belief_state['action']:
                        self.action_belief_state['action'][a] = 0
                    # TODO: these updates could be scaled by a normalized parse confidence
                    self.action_belief_state['action'][a] += inc
                    role_candidates_seen['action'].add(a)
                    if debug:
                        print "update_action_belief_from_grounding: adding count to action " + a + "; " + str(inc)

                    # Update patient and recipient, if present, with action tree args.
                    # These disregard argument order in favor of finding matching argument types.
                    # This gives us more robustness to bad parses with incorrectly ordered args or incomplete args.
                    # However, if we eventually have commands that take two args of the same type, we will
                    # have to introduce explicit ordering constraints here for those.
                    for r in ['patient', 'recipient']:
                        if r in roles and at.children is not None:
                            for cn in at.children:
                                if (r in self.action_args[a] and
                                        self.parser.ontology.types[cn.type] in self.action_args[a][r]):
                                    c = self.parser.ontology.preds[cn.idx]
                                    if c not in self.action_belief_state[r]:
                                        self.action_belief_state[r][c] = 0
                                    self.action_belief_state[r][c] += inc
                                    role_candidates_seen[r].add(c)
                                    if debug:
                                        print ("update_action_belief_from_grounding: adding count to " + r +
                                               " " + c + "; " + str(inc))

        # Else, just add counts as appropriate based on roles asked based on a trace of the whole tree.
        else:
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
                                self.action_belief_state[r][c] = 0
                            to_increment.append(c)
                    if cn.children is not None:
                        to_traverse.extend(cn.children)
                if len(to_increment) > 0:
                    inc = count / float(len(to_increment))
                    for c in to_increment:
                        self.action_belief_state[r][c] += inc
                        role_candidates_seen[r].add(c)
                        if debug:
                            print ("update_action_belief_from_grounding: adding count to " + r + " " + c +
                                   "; " + str(inc))

        # Decay counts of everything not seen per role (except None, which is a special filler for question asking).
        for r in roles:
            to_decrement = [fill for fill in self.action_belief_state[r] if fill not in role_candidates_seen[r]
                            and fill is not None]
            if len(to_decrement) > 0:
                inc = count / float(len(to_decrement))
                for td in to_decrement:
                    self.action_belief_state[r][td] -= inc
                    if debug:
                        print ("update_action_belief_from_grounding: subtracting count from " + r + " " + td +
                               "; " + str(inc))

    # Given a parse and a list of predicates, return the subtrees in the parse rooted at those predicates.
    # If a subtree is rooted beneath one of the specified predicates, it will not be returned (top-level only).
    def get_parse_subtrees(self, root, preds):
        debug = True
        if debug:
            print "get_parse_subtrees called for root " + self.parser.print_parse(root) + " and preds " + str(preds)

        trees_found = []
        pred_idxs = [self.parser.ontology.preds.index(p) for p in preds]
        if root.idx in pred_idxs:
            trees_found.append(root)
        elif root.children is not None:
            for c in root.children:
                trees_found.extend(self.get_parse_subtrees(c, preds))
        if debug:
            print "get_parse_subtrees: found trees " + str(trees_found)  # DEBUG
        return trees_found

    # Sample a discrete action from the current belief counts.
    # Each argument of the discrete action is a tuple of (argument, confidence) for confidence in [0, 1].
    def sample_action_from_belief(self, current_confirmed, arg_max=False):

        chosen = {r: (None, 0) if current_confirmed[r] is None else (current_confirmed[r], 1.0)
                  for r in self.roles}
        for r in [_r for _r in self.roles if current_confirmed[_r] is None]:

            min_count = min([self.action_belief_state[r][entry] for entry in self.action_belief_state[r]])
            mass = sum([self.action_belief_state[r][entry] - min_count for entry in self.action_belief_state[r]])
            if mass > 0:
                dist = [(self.action_belief_state[r][entry] - min_count) / mass
                        for entry in self.action_belief_state[r]]
                if arg_max:
                    max_idxs = [idx for idx in range(len(dist)) if dist[idx] == max(dist)]
                    c = np.random.choice([self.action_belief_state[r].keys()[idx] for idx in max_idxs], 1)
                else:
                    c = np.random.choice([self.action_belief_state[r].keys()[idx]
                                          for idx in range(len(self.action_belief_state[r].keys()))],
                                         1, p=dist)
                chosen[r] = (c[0], dist[self.action_belief_state[r].keys().index(c)])

        return chosen

    # Return a string question based on a discrete sampled action.
    def get_question_from_sampled_action(self, sampled_action, include_threshold):
        debug = True
        if debug:
            print "get_question_from_sampled_action called with " + str(sampled_action) + ", " + str(include_threshold)

        roles_to_include = [r for r in self.roles if sampled_action[r][1] >= include_threshold]
        if 'action' in roles_to_include:
            relevant_roles = ['action'] + [r for r in (self.action_args[sampled_action['action'][0]].keys()
                                           if sampled_action['action'][0] is not None else ['patient', 'recipient'])]
        else:
            relevant_roles = self.roles[:]
        confidences = {r: sampled_action[r][1] for r in relevant_roles}
        s_conf = sorted(confidences.items(), key=operator.itemgetter(1))
        if debug:
            print "get_question_from_sampled_action: s_conf " + str(s_conf)

        # Determine which args to include as already understood in question and which arg to focus on.
        least_conf_role = s_conf[0][0]
        if max([conf for _, conf in s_conf]) == 0.0:  # no confidence
            least_conf_role = None
        if debug:
            print ("get_question_from_sampled_action: roles_to_include " + str(roles_to_include) +
                   " with least_conf_role " + str(least_conf_role))

        # Ask a question.
        roles_in_q = []  # different depending on action selection
        if roles_to_include == self.roles:  # all roles are above threshold, so perform.
            if sampled_action['action'][0] == 'walk':
                q = "You want me to go to " + sampled_action['patient'][0] + "?"
                roles_in_q.extend(['action', 'patient'])
            else:
                q = ("You want me to deliver " + sampled_action['patient'][0] + " to " +
                     sampled_action['recipient'][0] + "?")
                roles_in_q.extend(['action', 'patient', 'recipient'])
        elif least_conf_role == 'action':  # ask for action confirmation
            if sampled_action['action'][0] is None:
                if 'patient' in roles_to_include:
                    q = "What should I do involving " + sampled_action['patient'][0] + "?"
                    roles_in_q.extend(['patient'])
                elif 'recipient' in roles_to_include:
                    q = "What should I do involving " + sampled_action['recipient'][0] + "?"
                    roles_in_q.extend(['recipient'])
                else:
                    q = "What kind of action should I perform?"
            elif sampled_action['action'][0] == 'walk':
                if 'patient' in roles_to_include:
                    q = "You want me to go to " + sampled_action['patient'][0] + "?"
                    roles_in_q.extend(['action', 'patient'])
                else:
                    q = "You want me to go somewhere?"
                    roles_in_q.extend(['action'])
            else:  # i.e. bring
                if 'patient' in roles_to_include:
                    if 'recipient' in roles_to_include:
                        q = ("You want me to deliver " + sampled_action['patient'][0] + " to "
                             + sampled_action['recipient'][0] + "?")
                        roles_in_q.extend(['action', 'patient', 'recipient'])
                    else:
                        q = "You want me to deliver " + sampled_action['patient'][0] + " to someone?"
                        roles_in_q.extend(['action', 'patient'])
                elif 'recipient' in roles_to_include:
                    q = "You want me to deliver something to " + sampled_action['recipient'][0] + "?"
                    roles_in_q.extend(['action', 'recipient'])
                else:
                    q = "You want me to deliver something for someone?"
                    roles_in_q.extend(['action'])
        elif least_conf_role == 'patient':  # ask for patient confirmation
            if sampled_action['patient'][0] is None:
                if 'action' in roles_to_include:
                    if sampled_action['action'][0] == 'walk':
                        q = "Where should I go?"
                        roles_in_q.extend(['action'])
                    elif 'recipient' in roles_to_include:
                        q = "What should I deliver to " + sampled_action['recipient'][0] + "?"
                        roles_in_q.extend(['action', 'recipient'])
                    else:  # i.e. bring with no recipient
                        q = "What should I find to deliver?"
                        roles_in_q.extend(['action'])
                else:
                    if 'recipient' in roles_to_include:
                        q = ("What else is involved in what I should do besides " +
                             sampled_action['recipient'][0] + "?")
                        roles_in_q.extend(['recipient'])
                    else:
                        q = "What is involved in what I should do?"
            else:
                if 'action' in roles_to_include:
                    if sampled_action['action'][0] == 'walk':
                        q = "You want me to walk to " + sampled_action['patient'][0] + "?"
                        roles_in_q.extend(['action', 'patient'])
                    elif 'recipient' in roles_to_include:
                        q = ("You want me to deliver " + sampled_action['patient'][0] + " to " +
                             sampled_action['recipient'][0] + "?")
                        roles_in_q.extend(['action', 'patient', 'recipient'])
                    else:
                        q = "You want me to deliver " + sampled_action['patient'][0] + " to someone?"
                        roles_in_q.extend(['action', 'patient'])
                else:
                    if 'recipient' in roles_to_include:
                        q = ("You want me to do something involving " + sampled_action['patient'][0] +
                             " for " + sampled_action['recipient'][0] + "?")
                        roles_in_q.extend(['patient', 'recipient'])
                    else:
                        q = "You want me to do something involving " + sampled_action['patient'][0] + "?"
                        roles_in_q.extend(['patient'])
        elif least_conf_role == 'recipient':  # ask for recipient confirmation
            if sampled_action['recipient'][0] is None:
                if 'action' in roles_to_include:
                    if sampled_action['action'][0] == 'walk':
                        raise ValueError("ERROR: get_question_from_sampled_action got a sampled action " +
                                         "with empty recipient ask in spite of action being walk")
                    elif 'patient' in roles_to_include:
                        q = "To whom should I deliver " + sampled_action['patient'][0] + "?"
                        roles_in_q.extend(['action', 'patient'])
                    else:  # i.e. bring with no recipient
                        q = "Who should receive what I deliver?"
                        roles_in_q.extend(['action'])
                else:
                    if 'patient' in roles_to_include:
                        q = "Who is involved in what I should do with " + sampled_action['patient'][0] + "?"
                        roles_in_q.extend(['patient'])
                    else:
                        q = "Who is involved in what I should do?"
            else:
                if 'action' in roles_to_include:
                    if 'patient' in roles_to_include:
                        q = ("You want me to deliver " + sampled_action['patient'][0] + " to " +
                             sampled_action['recipient'][0] + "?")
                        roles_in_q.extend(['action', 'patient', 'recipient'])
                    else:
                        q = "You want me to deliver something to " + sampled_action['recipient'][0] + "?"
                        roles_in_q.extend(['action', 'recipient'])
                elif 'patient' in roles_to_include:
                    q = ("You want me to do something with " + sampled_action['patient'][0] + " for " +
                         sampled_action['recipient'][0] + "?")
                    roles_in_q.extend(['patient', 'recipient'])
                else:
                    q = "You want me to do something for " + sampled_action['recipient'][0] + "?"
                    roles_in_q.extend(['recipient'])
        else:  # least_conf_role is None, i.e. no confidence in any arg, so ask for full restatement
            q = "Could you rephrase your request?"

        # Return the question and the roles included in it.
        # If the user affirms, all roles included in the question should have confidence boosted to 1.0
        # If the user denies, all roles included in the question should have their counts subtracted.
        return q, least_conf_role, roles_to_include, roles_in_q

    # Update the parser by re-training it from the current set of induced utterance/grounding pairs.
    def train_parser_from_induced_pairs(self, epochs, parse_reranker_beam, interpolation_reranker_beam,
                                        verbose=0):

        # Induce utterance/semantic form pairs from utterance/grounding pairs, then run over those induced
        # pairs the specified number of epochs.
        utterance_semantic_pairs = []
        for [x, g] in self.induced_utterance_grounding_pairs:

            parses = []
            cky_parse_generator = self.parser.most_likely_cky_parse(x, reranker_beam=parse_reranker_beam,
                                                                    debug=False)
            parse, score, _, _ = next(cky_parse_generator)
            while parse is not None and len(parses) < interpolation_reranker_beam:

                gs = self.grounder.ground_semantic_tree(parse.node)
                gn = self.sort_groundings_by_conf(gs)
                if len(gn) > 0:
                    gz, g_score = gn[0]  # top confidence grounding, which may be True/False
                    if ((type(gz) is bool and gz == g) or
                            (type(gz) is not bool and g.equal_allowing_commutativity(gz, self.parser.ontology))):
                        parses.append([parse, score + math.log(g_score)])
                        if verbose > 0:
                            print ("for x '" + str(x) + "' with grounding " + self.parser.print_parse(g) +
                                   " found semantic form " + self.parser.print_parse(parse.node, True) +
                                   " with scores p " + str(score) + ", g " + str(g_score))
                    parse, score, _, _ = next(cky_parse_generator)

            if len(parses) == 0 and verbose > 0:
                print ("no semantic parse found matching grounding for pair '" + str(x) +
                       "', " + self.parser.print_parse(g))

            best_interpolated_parse = sorted(parses, key=lambda t: t[1], reverse=True)[0][0]
            utterance_semantic_pairs.append([x, best_interpolated_parse.node])
            print "... re-ranked to choose " + self.parser.print_parse(best_interpolated_parse.node)

        self.parser.train_learner_on_semantic_forms(utterance_semantic_pairs, epochs=epochs,
                                                    reranker_beam=parse_reranker_beam, verbose=verbose)
