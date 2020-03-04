def time_reverse_primes(primes):
    """
    Computes the time reversal of the input system (under general asynchronous update).
    The time reverse system has the same STG as the input system, but with each edge reversed.

    Input:
    primes - PyBoolNet prime dictionary specifying the update rules

    Ouput:
    trprimes - PyBoolNet prime dictionary specifying the update rules of the time-reversed system
    """
    trprimes = {}
    for k,v in primes.items():
        trv = [[],[]]
        for i in [0,1]:
            for p in v[i]:
                pc = p.copy()
                if k in pc: pc[k] = int(not pc[k])
                trv[int(not i)].append(pc)
        trprimes[k]=trv.copy()
    return trprimes
