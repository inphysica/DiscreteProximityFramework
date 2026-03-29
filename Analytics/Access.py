from datetime import datetime, timedelta
import math

def LogisticDicay(x, Plato, Half):

    if x < Plato: return 1
    if x > Plato + 2 * Half: return 0

    # 

    return (1 / (1 + math.exp(math.log(2000) / Half * (x - Plato - Half)))) 


    x0 = x-Plato

    if x0 < 0:

         return 1

    else:

        growth_rate = math.log(9999) / Half
        g = 1 - (1 / (1 + math.exp(-growth_rate * (x0 - Half))))

        return g




# Analytics.Reach_wDecay(Park_ODM, 400, 200, Park_W)




def PTODM_ByOrigin(  PTAccess, PTTravel, WalkingODM, OriginSelection, DestinationSelection, max_total_duration, max_walking_duration = 15, max_direct_walking_duration = 15, bar = None):


    """
    DESCRIPTION:

        This function return all stations from 
    
    INPUT:

        PTAccess            : [Origin|Destination][PT Stop] = (distance, duration)
                             
                            We keep orign and destination both in same position.
                            This saves memory and time.

        PTTravel            : [PT Stop][PT Stop] = (Duration, InitialWaiting, CumulativeWalking)

                            Duration is without Initial waiting
                            CumulativeWalking is only walks between stations since we start trips from station and end in statations.

        WalkingODM          : [Origin][Destination] = (distance, duration)
                        
        DestinationSelection  : [Destination]

                            We only evaluate these destination which have value but value itself is NOT used!

        OriginSelection     : [Origin]

        max_total_duration > maximum duration one can reach destination by PT + walking. This is the main parameter to set the range of the analysis.
        max_walking_duration > maximum duration one can walk to reach a station. This is the main parameter to set the range of the analysis.
        max_direct_walking_duration > maximum duration one can walk directly to destination. This is the main parameter to set the range of the analysis.




    RETURN:

        ODM                 : [origin][destination] = best duration betweeen origin to destintion.  Origin and destinations can be 

        # Sations             : [origin][station][destinations] 

    
    """


    stamp_0 = datetime.now()

    skipped = 0
    ValidPT_byDestination = {}

    list_of_missing_destination = ["PosID"]

    bar.setMaximum(len(DestinationSelection))
    bar.setValue(0)
    bar.repaint()

    for i, grd_id in enumerate(DestinationSelection):
        
        bar.setValue(i)
        bar.repaint()
        
        ValidPT_byDestination[grd_id] = {}

        if grd_id not in PTAccess:
            
            list_of_missing_destination.append(grd_id)
            skipped+= 1
            continue

        for pt in PTAccess[grd_id]:
            distance_walking, duration_walking = PTAccess[grd_id][pt]

            if duration_walking > max_walking_duration:
                
                continue

            ValidPT_byDestination[grd_id][pt] = duration_walking

    print( " -> total: %s skipped: %s kept: %s" % (len(DestinationSelection), skipped, len(DestinationSelection) - skipped))

    if len(DestinationSelection) - skipped == 0:
        print("There are no destination in range!")
        return None, None, None
    
    hasSelection = False
    if len(OriginSelection) > 0:
        hasSelection = True

    ODM = {}

    bar.setMaximum(len(PTAccess))
    bar.setValue(0)
    bar.repaint()

    for i, o in enumerate(PTAccess):

        bar.setValue(i)
        bar.repaint()

        if hasSelection:
            if o not in OriginSelection:
                continue


        ODM[o] = {} 

        best_duration_byExit = {} # [last stop] =  best duration

        for pt0 in PTAccess[o]:

            distance, duration_walking  = PTAccess[o][pt0]

            if duration_walking > max_walking_duration:
                continue
            
            if pt0 not in PTTravel:
                continue

            for pt1 in PTTravel[pt0]:

                Duration, InitialWaiting, CumulativeWalking = PTTravel[pt0][pt1] 
                travel_duration = Duration

                cumulative_duration =  travel_duration + duration_walking

                if cumulative_duration > max_total_duration:
                    continue

                if pt1 not in best_duration_byExit:
                    best_duration_byExit[pt1] = cumulative_duration
                else:
                    best_duration_byExit[pt1]= min( cumulative_duration, best_duration_byExit[pt1] )


        # we only look last step for set

        s = 0

        for destination in ValidPT_byDestination:

            L = []

            for pt1 in ValidPT_byDestination[destination]:

                if pt1 not in best_duration_byExit:
                    continue
            
                walking_duration_toDestination = ValidPT_byDestination[destination][pt1]
                cumulative_duration = best_duration_byExit[pt1]

                total_duration = cumulative_duration + walking_duration_toDestination

                if total_duration > max_total_duration:
                    continue

                L.append(total_duration)

            if len(L) == 0:
                # we can not reach destination by PT, check if we can walk directly
                continue

            else:

                L.sort()

                traveling_duration =  L[0]
                walking_distance = walking_duration = float("inf")
                
                if o in WalkingODM:
                    if destination in WalkingODM[o]:

                        walking_distance, walking_duration = WalkingODM[o][destination]

                        if walking_duration > max_direct_walking_duration:
                            walking_duration = float("inf")

                best_duration = min(traveling_duration, walking_duration)

                if o == destination:
                    best_duration = 0

                ODM[o][destination] = best_duration

            if destination not in DestinationWeights:
                s += 0
            else:
                s += DestinationWeights[destination]


    return ODM