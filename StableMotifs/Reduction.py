import PyBoolNet
import itertools as it
import networkx as nx
import re

import StableMotifs.TimeReversal as sm_time
import StableMotifs.RestrictSpace as sm_rspace
import StableMotifs.Format as sm_format
import StableMotifs.Succession as sm_succession

def simplify_primes(primes):
    """
    Simplifies PyBoolNet primes (e.g., A | A & B becomes A)

    Input:
    primes - PyBoolNet primes describing the system update rules

    Output:
    a simplified version of primes
    """
    # reimport to force simplification
    if len(primes) > 0:
        return PyBoolNet.FileExchange.bnet2primes(PyBoolNet.FileExchange.primes2bnet(primes))
    else:
        return primes

def reduce_primes(fixed,primes):
    """
    Simplifies boolean rules when some nodes are held fixed

    Inputs:
    fixed - a dictionary of node states that are held fixed
    primes - PyBoolNet primes describing the system update rules

    Outputs:
    reduced_primes - PyBoolNet primes decribing the simplified update rules
    percolated_states - a dictionary of fixed node states (including the inputs) that were simplified and removed
    """
    reduced_primes = PyBoolNet.PrimeImplicants.create_constants(primes,fixed,Copy=True)
    percolated_states = PyBoolNet.PrimeImplicants._percolation(reduced_primes,True)
    percolated_states.update(fixed)


    return simplify_primes(reduced_primes), percolated_states

def delete_node(primes, node):
    G = PyBoolNet.InteractionGraphs.primes2igraph(primes)

    assert not G.has_edge(node,node), ' '.join(["Node",str(node),"has a self-loop and cannot be deleted."])

    new_primes = {k:v for k,v in primes.items() if not k == node}

    rule1 = sm_format.rule2bnet(primes[node][1])

    for child in G.successors(node):
        crule = sm_format.rule2bnet(primes[child][1])
        print("BEFORE",crule)
        print("SUB:",node,"->","("+rule1+")")
        crule = re.sub(rf'\b{node}\b',"("+rule1+")",crule)
        crule = PyBoolNet.BooleanLogic.minimize_espresso(crule)
        print("AFTER",crule)
        crule = child + ",\t" + crule

        new_primes[child] = PyBoolNet.FileExchange.bnet2primes(crule)[child]
        PyBoolNet.PrimeImplicants._percolation(new_primes,True)
    return new_primes

def remove_outdag(primes):
    G = PyBoolNet.InteractionGraphs.primes2igraph(primes)
    od = PyBoolNet.InteractionGraphs.find_outdag(G)
    reduced = primes.copy()
    for node in od:
        if node in reduced:
            reduced = delete_node(reduced, node)
    return reduced

def deletion_reduction(primes, max_in_degree = float('inf')):
    reduced = remove_outdag(primes)
    G = PyBoolNet.InteractionGraphs.primes2igraph(reduced)
    cur_order = sorted(reduced,key=lambda x: G.in_degree(x))

    change = True
    while change and len(reduced) > 0:
        change = False
        for node in cur_order:
            retry_node = True
            if not node in reduced or G.in_degree(node) > max_in_degree:
                continue
            elif not any([node in p for p in reduced[node][1]]):
                reduced = delete_node(reduced, node)
                G = PyBoolNet.InteractionGraphs.primes2igraph(reduced)
                change = True
                break
        cur_order = sorted(reduced,key=lambda x: G.in_degree(x))

    return reduced

def mediator_reduction(primes):
    """
    Network reduction method of Saadadtpour, Albert, Reluga (2013)
    Preserves number of fixed points and complex attractors, but may change
    qualitative features of complex attractors.
    """

    reduced = remove_outdag(primes)
    cur_order = sorted(reduced)
    G = PyBoolNet.InteractionGraphs.primes2igraph(reduced)
    candidates = [v for v in reduced if G.in_degree(v) == G.out_degree(v) == 1 and not G.has_edge(v,v)]
    return reduced
    for node in candidates:
        u = list(G.predecessors(node))[0]
        w = list(G.successors(node))[0]
        if not w in G.successors(u) and not w in G.predecessors(u):
            reduced = delete_node(reduced, node)
            G = PyBoolNet.InteractionGraphs.primes2igraph(reduced)
            candidates = [v for v in reduced if G.in_degree(v) == G.out_degree(v) == 1 and not G.has_edge(v,v)]

    return reduced


class MotifReduction:
    """
    A reduced network with additional information stored;
    represents a node in a succession diagram (see Succession.py)

    Variables:
    motif_history - list of stable motifs that can lock in to give the reduced network (in order)
    merged_history_permutations - list of permutations of motif_history (by index) that are also valid
    logically_fixed_nodes - node state dictionary describing nodes that have been
                            fixed and reduced by stable motifs and their
                            logical domain of influence
    reduced_primes - update rules of the reduced network as PyBoolNet primes
    time_reverse_primes - update rules of the time reversed system as PyBoolNet primes
    stable_motifs - list of stable motifs in the reduced network
    time_reverse_stable_motifs - list of stable motifs in the time reversed system
    merged_source_motifs - stable motifs generated by merging the stable motifs corresponding to source nodes
    source_independent_motifs - stable motifs that exist independent of the values of the source nodes

    rspace - the rspace, or "restrict space" of the reduced network, describing a
             necessary condition for the system to avoid activating additional
             stable motifs (see RestrictSpace.py)
    fixed_rspace_nodes - nodes that are fixed in the rspace (stored as a state dictionary)
    rspace_constraint - a Boolean expression that is true in and only in the rspace
    reduced_rspace_constraint - a simplification of the rspace_constraint given
                                the fixed_rspace_nodes states are satisfied
    rspace_update_primes - the update rules obtained from simplifying under the
                           assumption that the fixed_rspace_nodes are fixed
    conserved_functions - a list of Boolean functions that are constant within
                          every attractor, in PyBoolNet update rule format
    rspace_attractor_candidates - attractors in the rspace_update_primes that
                                  satisfy the reduced_rspace_constraint

    partial_STG - subgraph of the state transition graph of the reduced network
                  that contains any and all attractors that do not lie in any
                  of the reduced network's stable motifs
    no_motif_attractors - list of complex attractors that do not "lock in" any additional stable motifs

    Functions:
    __init__(self,motif_history,fixed,reduced_primes,search_partial_STGs=True,prioritize_source_motifs=True)
    merge_source_motifs(self) - merges source node motifs into larger multi-node motifs for efficiency
    test_rspace(self) - for building rspace_attractor_candidates
    build_K0(self) - helper function for build_partial_STG
    build_inspace(self,ss,names) - helper function for build_partial_STG
    build_partial_STG(self) - for building partial_STG
    find_no_motif_attractors(self) - finds no_motif_attractors
    summary(self) - prints a summary of the MotifReduction to screen
    """
    def __init__(self,motif_history,fixed,reduced_primes,search_partial_STGs=True,prioritize_source_motifs=True):
        if motif_history is None:
            self.motif_history = []
        else:
            self.motif_history = motif_history.copy()
        self.merged_history_permutations = []
        self.logically_fixed_nodes = fixed
        self.reduced_primes = reduced_primes.copy()

        self.time_reverse_primes =sm_time.time_reverse_primes(self.reduced_primes)
        self.stable_motifs = PyBoolNet.AspSolver.trap_spaces(self.reduced_primes, "max")
        self.time_reverse_stable_motifs = PyBoolNet.AspSolver.trap_spaces(self.time_reverse_primes, "max")

        self.merged_source_motifs=None
        self.source_independent_motifs=None
        if self.motif_history == [] and prioritize_source_motifs:
            self.merge_source_motifs()

        self.rspace = sm_rspace.rspace(self.stable_motifs,self.reduced_primes)

        # These may or may not get calculated.
        # Sensible default values are in comments, but we will just use None for now.
        self.fixed_rspace_nodes=None # {}
        self.rspace_constraint=None # ""
        self.reduced_rspace_constraint=None # ""
        self.rspace_update_primes=None # {}
        self.conserved_functions=None # [[{}]]
        self.rspace_attractor_candidates=None # []
        self.partial_STG=None # nx.DiGraph()
        self.no_motif_attractors=None # []

        study_possible_oscillation = False
        if not self.merged_source_motifs is None:
            self.terminal = "no"
        elif self.rspace == [[{'0':1}]] and len(self.stable_motifs) > 0: # a stable motif must lock in
            self.terminal = "no"
        elif self.rspace == [[{}]] and len(self.stable_motifs) > 0: # could not find 1-node drivers
            self.terminal = "possible"
            study_possible_oscillation = True
        elif len(self.stable_motifs) == 0: # necessarily terminal
            self.terminal = "yes"
            if len(self.reduced_primes) > 0: # Terminates in oscillation, else, fixed point
                study_possible_oscillation = True
        else: # found 1-node drivers, so we can investigate further
            self.terminal = "possible" # TODO: implement case-checking based on rspace
            self.fixed_rspace_nodes =sm_rspace.fixed_rspace_nodes(self.rspace,self.reduced_primes)

            for motif in self.stable_motifs:
                if motif.items() <= self.fixed_rspace_nodes.items():
                    self.terminal = "no"
                    break
            if self.terminal == "possible":
                self.rspace_constraint = sm_format.pretty_print_rspace(self.rspace)
                self.reduced_rspace_constraint = sm_rspace.reduce_rspace_string(self.rspace_constraint,self.fixed_rspace_nodes)
                self.rspace_update_primes = reduce_primes(self.fixed_rspace_nodes,self.reduced_primes)[0]
                #self.test_rspace(search_partial_STGs = search_partial_STGs)

            study_possible_oscillation = self.terminal == "possible" # value may be changed by test_rspace
        if study_possible_oscillation:
            if search_partial_STGs:
                if self.rspace_update_primes is not None and len(self.rspace_update_primes) > 30:
                    print("STG is too large ("+str(len(self.reduced_primes))+"). Giving up.")
                    return
                elif len(self.reduced_primes) > 30:
                    print("STG is too large ("+str(len(self.reduced_primes))+"). Giving up.")
                    return
                self.find_no_motif_attractors()
                if len(self.no_motif_attractors) == 0:
                    self.terminal = "no"
                else:
                    self.terminal = "yes"
                    self.conserved_functions = sm_rspace.attractor_space_candidates(self.stable_motifs,
                                                                         self.time_reverse_stable_motifs)

    def merge_source_motifs(self):
        """
        Merges stable motifs (and time-reversal stable motifs) that correspond to source nodes, e.g. A*=A, into combined motifs to
        avoid combinatorial explosion. For example, A*=A, B*=B, C*=C produces six motifs that can stabilize in 8 ways; without
        merging, these 8 combinations lead to 8*3!=48 successions because they can be considered in any order. This is silly because
        source nodes all stabilize simultaneously.

        We will assume that stable motifs and time reverse stable motifs have already been computed.

        Note that a source node in the forward time system is a source node in the time reverse system as well.
        This follows from A* = A => A- = ~(A*(A=~A)) = ~(~A) = A.

        If A* = A or X (i.e., A=1 is a stable motif), then A- = ~(~A | X) = A & ~X, so A=0 is a time-reverse stable motif. A similar
        argument applies for the A=0 stable motif. Thus, a motif is only a source motif if it is also a time-reverse motif.
        """
        source_motifs = [x for x in self.stable_motifs if len(x) == 1 and x in self.time_reverse_stable_motifs]
        if source_motifs == []:
            return
        self.source_independent_motifs = [x for x in self.stable_motifs if not x in source_motifs]

        source_vars = list(set([next(iter(x.keys())) for x in source_motifs])) # a list of source nodes

        self.merged_source_motifs = []
        for state in it.product([0,1],repeat=len(source_vars)):
            self.merged_source_motifs.append({v:x for v,x in zip(source_vars,state)})


    # def attractor_satisfies_constraint(attractor, names, constraint):
    #     possible_attractor = True
    #     for state in attractor:
    #         state_dict = {** sm_format.statestring2dict(state,names)}
    #         if PyBoolNet.BooleanLogic.are_mutually_exclusive(constraint,
    #                                                          sm_format.implicant2bnet(state_dict)):
    #             possible_attractor = False
    #             break
    #     return possible_attractor

    def test_rspace(self, search_partial_STGs=True):
        #
        #
        # rdiag = build_succession_diagram(self.rspace_update_primes,search_partial_STGs=False)
        # for fn in rdiag.attractor_fixed_nodes_list:
        #     if PyBoolNet.BooleanLogic.are_mutually_exclusive(self.rspace_constraint,
        #                                                      sm_format.implicant2bnet(fn)):
        #         return
        #
        # if not search_partial_STGs:
        #     return
        STG=PyBoolNet.StateTransitionGraphs.primes2stg(self.rspace_update_primes,"asynchronous")
        steady_states,complex_attractors=PyBoolNet.Attractors.compute_attractors_tarjan(STG)
        names = sorted(self.rspace_update_primes)
        attractors = complex_attractors+[[s] for s in steady_states]
        self.rspace_attractor_candidates = []

        for attractor in attractors:
            possible_rspace_attractor = True
            for state in attractor:
                state_dict = {** sm_format.statestring2dict(state,names),**self.fixed_rspace_nodes}
                if PyBoolNet.BooleanLogic.are_mutually_exclusive(self.rspace_constraint,
                                                                 sm_format.implicant2bnet(state_dict)):
                    possible_rspace_attractor = False
                    break
            if possible_rspace_attractor:
                self.rspace_attractor_candidates.append(attractor)

        if len(self.rspace_attractor_candidates) == 0:
            self.terminal = "no"

    # Helper function for smart STG building
    def build_K0(self):
        K = set()
        for sm in self.stable_motifs:
            fill_vars = [k for k in self.reduced_primes if not k in sm]
            for fills in it.product(['0','1'],repeat = len(fill_vars)):
                s = ''
                fi = 0
                for k in self.reduced_primes:
                    if k in sm:
                        s += str(sm[k])
                    else:
                        s += fills[fi]
                        fi += 1
                K.add(s)
        return K

    #def contradicts_reduced_rspace(self,ss,names,rnames):
    #    state_dict =
    #    return not PyBoolNet.BooleanLogic.are_mutually_exclusive(self.reduced_rspace_constraint,
    #                                                        sm_format.implicant2bnet(state_dict))

    def in_motif(self,ss,names):
        for sm in self.stable_motifs:
            smin = True
            for i,r in enumerate(names):
                if r in sm and not int(ss[i]) == sm[r]:
                    smin = False
            if smin: return True
        return False

    # Helper function for smart STG building
    # List all tr stable_motifs to which state ss belongs
    def build_inspace(self,ss,names):
        inspaces = []
        for ts in self.time_reverse_stable_motifs:
            tsin = True
            for i,r in enumerate(names):
                if r in ts and not int(ss[i]) == ts[r]:
                    tsin = False
            if tsin: inspaces.append(ts)
        return inspaces

    def build_partial_STG(self):
        names = sorted(self.reduced_primes)
        name_ind = {n:i for i,n in enumerate(names)}

        if self.rspace_update_primes is not None:
            rnames = sorted(self.rspace_update_primes)
            rname_ind = {n:i for i,n in enumerate(names) if n in rnames}
            fixed = self.fixed_rspace_nodes
        else:
            rnames = names.copy()
            rname_ind = name_ind.copy()
            fixed = {}



        # G = PyBoolNet.InteractionGraphs.primes2igraph(self.reduced_primes)
        # ignored = PyBoolNet.InteractionGraphs.find_outdag(G)
        # C = nx.condensation(G)
        #
        # sim_names = [x for x in names if not x in fixed and not x in ignored]
        sim_names = [x for x in names if not x in fixed]
        # s_inds = {}
        # j = 0
        # for n in names:
        #     if n in sim_names:
        #         s_inds[n] = j
        #         j += 1
        # print("NUMBERS",len(names),len(sim_names) ,len(fixed),len(ignored))
        # topological_order = []
        # for x in nx.topological_sort(C):
        #     topological_order += [s_inds[y] for y in C.nodes[x]['members'] if y in sim_names]
        # topological_order.reverse()
        #N = len(names)

        #K = self.build_K0()
        K = set()
        self.partial_STG = nx.DiGraph()

        inspace_dict = {}
        t = 0
        T = 1
        # note: product order gives s counting up in binary from 00..0 to 11..1
        for s in it.product(['0','1'],repeat=len(sim_names)):
            # if t > T:
            #     T*=2
            #     print(t,"/",2**len(sim_names))
            # t+=1

            # s_topo = [s[k] for k in topological_order]
            sl = ['']*len(names)
            j = 0
            for i in range(len(names)):
                if names[i] in fixed:
                    sl[i] = str(fixed[names[i]])
                # elif names[i] in ignored:
                #     sl[i] = '2'
                else:
                    sl[i] = s[j]#s_topo[j]
                    j += 1

            ss = ''.join(sl)

            if ss in K: continue
            if self.in_motif(ss,names): continue
            #if self.contradicts_reduced_rspace(ss,names): continue

            simstate = True

            inspace = self.build_inspace(ss,names)
            inspace_dict[ss] = inspace

            self.partial_STG.add_node(ss) # might end up removing later
            for i,r in enumerate(names):
                nri = int(not int(ss[i]))
                # if any p below is satisfied, we get a change of state
                # the value of the new r will be equal to nri
                for p in self.reduced_primes[r][nri]:
                    psat = True
                    for k,v in p.items():
                        if not int(ss[name_ind[k]]) == v:
                            psat = False
                            break
                    if psat: # state change verified
                        child_state_list = list(ss)
                        child_state_list[i] = str(nri)
                        child_state = ''.join(child_state_list)

                        # Check if changed something that should be fixed or landed in K
                        # If not, check if we left a TR stable motif
                        prune = r in fixed or child_state in K
                        if not prune:
                            if not child_state in inspace_dict:
                                inspace_dict[child_state] = self.build_inspace(child_state,names)
                            prune = not inspace_dict[child_state] == inspace
                        # By here, prune is TRUE if we left a TR motif or are in K

                        if prune:
                            # prune the STG and stop simulating ss
                            simstate = False
                            rnodes = list(nx.bfs_tree(self.partial_STG,ss,reverse=True).nodes())
                            K.update(rnodes)
                            self.partial_STG.remove_nodes_from(rnodes)
                        else:
                            self.partial_STG.add_edge(ss,child_state)
                        break # we know the ss at r changed, no need to check more primes
                if not simstate: break # don't check other vars: already found ss -> K

    def find_no_motif_attractors(self):
        if self.partial_STG is None:
            self.build_partial_STG()
        self.no_motif_attractors = list(nx.attracting_components(self.partial_STG))

    def summary(self,show_original_rules=True,show_explicit_permutations=False):
        print("Motif History:",self.motif_history)
        print()
        print("Logically Fixed Nodes:",self.logically_fixed_nodes)
        print()
        if not self.motif_history == []:
            print("Reduced Update Rules:")
            sm_format.pretty_print_prime_rules(self.reduced_primes)
        else:
            if show_original_rules:
                print("Original Update Rules:")
                sm_format.pretty_print_prime_rules(self.reduced_primes)
            else:
                print("The update rules are not reduced.")
        print()
        if self.terminal == "no":
            if self.merged_source_motifs is None:
                print("At least one additional stable motif must stabilize.")
                print()
                print("Stable motifs:", self.stable_motifs)
            else:
                print("Source node values are not yet specified for the following nodes:",
                       ', '.join(sorted([k for k in self.merged_source_motifs[0]])))
                print()
                if self.source_independent_motifs == []:
                    print("There are no source-independent stable motifs.")
                else:
                    print("The following stable motifs exist independently of the source configuration:")
                    print(self.source_independent_motifs)
        elif self.terminal == "yes":
            if len(self.reduced_primes) > 0:
                print("There is a complex attractor in this reduced system in which no additional stable motifs activate.")
                print("At least some of the following must oscillate in such an attractor:")
                print(list(self.reduced_primes.keys()))
            else:
                print("This branch terminates in a steady state.")
        elif self.terminal == "possible":
            print("Some or none of these stable motifs may stabilize:",
                  self.stable_motifs)
            print()
            if not self.fixed_rspace_nodes is None:
                print("If no more stable motifs stabilize, these node states must be fixed:",
                      self.fixed_rspace_nodes)
                print()
                print("In addition, the following must stabilize to TRUE:")
                print(self.reduced_rspace_constraint)
                print()
                print("In this case, the unfixed nodes update according to the following rules:")
                sm_format.pretty_print_prime_rules(self.rspace_update_primes)

        if not self.conserved_functions is None:
            print()
            if len(self.conserved_functions) > 0:
                print("Found the following functions that are constant on attractors in this branch:")
                for x in self.conserved_functions:
                    if len(x) > 0:
                        sm_format.pretty_print_rspace([x],silent=False)
                        print()
            else:
                print("Unable to find non-trivial conserved functions for attractors in this branch.")
                print()
            if not self.no_motif_attractors is None:
                if len(self.no_motif_attractors) > 0:
                    print("Found the following complex attractors that do not lock in additional stable motifs:")
                    for x in self.no_motif_attractors:
                        print(x)

        if len(self.merged_history_permutations) > 0:
            print()
            print("This branch contains the following motif_history permutation(s):")
            if show_explicit_permutations:
                for x in self.merged_history_permutations: print([self.motif_history[i] for i in x])
            else:
                for x in self.merged_history_permutations: print(x)
