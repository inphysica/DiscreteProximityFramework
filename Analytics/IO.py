import sqlite3
import json
from datetime import datetime, timedelta
import os
import time

# from tqdm import tqdm

import sys


from qgis.PyQt.QtWidgets import QDialog, QPushButton, QLineEdit, QFileDialog, QMessageBox, QProgressBar
from qgis.PyQt.QtCore import QCoreApplication


def quick_estimate_from_filesize(filepath):
    """
    Quick estimate of load time based only on file size - no database queries.
    Useful for instant feedback before showing full info.
    
    Returns:
        dict with keys: 'estimated_seconds', 'estimated_string', 'file_size_mb'
    """
    try:
        # Get file size
        file_size_bytes = os.path.getsize(filepath)
        file_size_mb = file_size_bytes / (1024 * 1024)
        
        # Estimate based on typical SQLite performance:
        # - Read speed: ~50 MB/s on SSD
        # - Processing overhead: ~0.5x of read time for parsing/dict ops
        read_speed_mb_s = 60  # MB/s for modern SSD
        processing_factor = 1.5  # 50% overhead for parsing
        
        total_estimated_time = (file_size_mb / read_speed_mb_s) * processing_factor
        
        # Format as human-readable string
        if total_estimated_time < 1:
            time_string = f"~{total_estimated_time*1000:.0f} ms"
        elif total_estimated_time < 60:
            time_string = f"~{total_estimated_time:.1f}s"
        else:
            minutes = int(total_estimated_time // 60)
            seconds = int(total_estimated_time % 60)
            time_string = f"~{minutes}m {seconds}s"
        
        return {
            'estimated_seconds': total_estimated_time,
            'estimated_string': time_string,
            'file_size_mb': file_size_mb
        }
        
    except Exception as e:
        return {
            'estimated_seconds': 0,
            'estimated_string': "Unknown",
            'file_size_mb': 0,
            'error': str(e)
        }

def get_sqlite_info(filepath):
    """
    Get detailed information about the SQLite ODM file.
    
    Returns:
        dict with file info, row counts, and table details
    """
    try:
        file_size_bytes = os.path.getsize(filepath)
        file_size_mb = file_size_bytes / (1024 * 1024)
        
        conn = sqlite3.connect(filepath)
        cursor = conn.cursor()
        
        # Get OD table row count
        cursor.execute("SELECT COUNT(*) FROM OD")
        total_rows = cursor.fetchone()[0]
        
        # Get unique origins and destinations
        cursor.execute("SELECT COUNT(DISTINCT origin) FROM OD")
        unique_origins = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT destination) FROM OD")
        unique_destinations = cursor.fetchone()[0]
        
        # Get distance statistics
        cursor.execute("SELECT MIN(distance), MAX(distance), AVG(distance) FROM OD")
        min_dist, max_dist, avg_dist = cursor.fetchone()
        
        conn.close()
        
        return {
            'file_size_mb': file_size_mb,
            'total_rows': total_rows,
            'unique_origins': unique_origins,
            'unique_destinations': unique_destinations,
            'min_distance': min_dist,
            'max_distance': max_dist,
            'avg_distance': avg_dist,
            'rows_per_origin': total_rows / unique_origins if unique_origins > 0 else 0
        }
        
    except Exception as e:
        print(f"Error getting SQLite info: {str(e)}")
        return {'error': str(e)}

def read_ODM( filepath, remove_prefix = True, origin_prefix_whitelist = [], destination_prefix_whitelist = [], max_duration = 0, bar = None, selection = None, limit=0, only_duration = False):


    """

    DESCRIPTION:
            Read ODM from SQLite file and return as nested dictionary.
            Can filter by origin/destination prefixes, max duration, and selection of origins.

    ARGUMENTS:
        filepath            : path to SQLite ODM file
        remove_prefix       : if True, remove any prefix before "-" in origin/destination IDs
        origin_prefix_whitelist      : list of allowed prefixes for origins (e.g. ["EE", "PT"])
        destination_prefix_whitelist : list of allowed prefixes for destinations (e.g. ["EE", "PT"])
        max_duration        : if > 0, only include entries with duration <= max_duration    
        bar                 : QProgressBar to update during loading (optional)
        selection           : list of origin IDs to include (optional)
        limit               : if > 0, only include entries with distance <= limit
        only_duration       : if True, D[origin][destination] = duration instead of (distance, duration)
        
    RETURN:
        D[origin][destination] = (distance, duration)
        if only_duration is True, then D[origin][destination] = duration



    """

    print( "read ODM: " + filepath)

    hasOriginPrefixWhitelist = False
    hasDestinationPrefixWhitelist = False

    if len(origin_prefix_whitelist) > 0:
        hasOriginPrefixWhitelist = True

    if len(destination_prefix_whitelist) > 0:
        hasDestinationPrefixWhitelist = True
    

    if bar is not None:
        bar.setMaximum(1)
        bar.setValue(0)
        bar.repaint()
        QCoreApplication.processEvents()

    # print( "read ODM: " + filepath)

    stamp_0 = datetime.now()

    D = {}

    conn = sqlite3.connect(filepath)
    # conn.execute('PRAGMA query_only = ON; ')
    # conn.execute('PRAGMA journal_mode = OFF; ')
    # conn.execute('PRAGMA cache_size = -100000; ')
    # conn.execute('PRAGMA mmap_size = 268435456; ')
    
    cursor = conn.cursor()
    query = "SELECT * FROM OD"
    if selection is not None and len(selection) > 0:
        query += " WHERE origin IN (%s)" % ",".join( ["'%s'" % s for s in selection] )
        if limit > 0:
            query += " AND distance <  %s" % limit
    else:
        if limit > 0:
            query += " WHERE distance <  %s" % limit


    print( query )

    cursor.execute(query)
    rows = cursor.fetchall()

    skipped = 0

    stat = 0

    if bar is not None:
        bar.setMaximum(len(rows))
        bar.setValue(0)
        bar.repaint()
        QCoreApplication.processEvents()


    print( " -> total rows in ODM: %s" % len(rows) )

    if len(rows) == 0:
        print(" -> No rows in ODM!")
        return None

    for row in rows:
        stat += 1

        if bar is not None and stat % 50 == 0:
            bar.setValue(stat)
            QCoreApplication.processEvents()

        origin = row[0]
        destination = row[1]
        distance = row[2]
        duration = row[3]


        # if origin == "EE-125mN6590375E542375":
        #     print(duration, max_duration)

        if remove_prefix:
            if "-" in origin:
                origin = origin.split("-")[-1]
            if "-" in destination:
                destination = destination.split("-")[-1]

        if hasOriginPrefixWhitelist:
            valid = False
            for prefix in origin_prefix_whitelist:
                if origin[:len(prefix)] == prefix:
                    valid = True
                    break
            if not valid:
                skipped += 1
                continue

        if hasDestinationPrefixWhitelist:
            valid = False
            for prefix in destination_prefix_whitelist:
                if destination[:len(prefix)] == prefix:
                    valid = True
                    break
            if not valid:
                skipped+= 1
                continue

        if max_duration > 0:

            if duration > max_duration:
                skipped += 1
                continue

        if origin not in D:
            D[origin] = {}


        if only_duration:
            D[origin][destination] = duration
        else:
            D[origin][destination] = (distance, duration)

        # if "PT" in origin and "GRD" in destination:
        #     stat += 1

    time_diff = datetime.now() - stamp_0
    print( " -> time:  %s[s]" % time_diff)
    print( " -> total: %s skipped: %s kept: %s" % (len(rows), skipped , len(rows) - skipped ))
    print( " -> unique origins: %s" % len(D))

    # if "EE-125mN6590375E542375" in D:
    #     print("Example entry for EE-125mN6590375E542375:", D["EE-125mN6590375E542375"])
    # else:
    #     print("Example entry for EE-125mN6590375E542375 not found in D")

    return D

def read_GTFS(filepath, max_duration = 0, bar = None):

    PT = {}

    """
        
    RETURN:
        D[origin][destination] =  (Duration, InitialWaiting, CumulativeWalking)


    """

    print( "read GTFS: " + filepath)

    stamp_0 = datetime.now()

    PT = {}

    PT_start = {} # entrance stop
    PT_end = {} # exit stop


    conn = sqlite3.connect(filepath)
    cursor = conn.cursor()
    query = "SELECT  origin, destination, InitialWaiting, CumulativeDuration, CumulativeWalking  FROM Results"
    cursor.execute(query)
    rows = cursor.fetchall()

    skipped = 0

    # self.labelCurrentStatus.setText("reading GTFS data...")
    # self.repaint()

    if bar is not None:
        bar.setMaximum(len(rows))
        bar.setValue(0)
        bar.repaint()
        QCoreApplication.processEvents()

    for idx, row in enumerate(rows):
        if bar is not None:
            bar.setValue(idx)
            bar.repaint()
            QCoreApplication.processEvents()

        origin = row[0]
        destination = row[1]
        InitialWaiting = row[2]
        CumulativeDuration = row[3]
        CumulativeWalking = row[4]

        Duration = CumulativeDuration - InitialWaiting

        if (max_duration > 0):
            if Duration > max_duration:
                skipped+=1 
                continue

        if origin not in PT:
            PT[origin] = {}

        PT[origin][destination] = (Duration, InitialWaiting, CumulativeWalking)

        if origin not in PT_start:
            PT_start[origin] = 0

        if destination not in PT_end:
            PT_end[destination] = 0
            
        PT_start[origin] += 1
        PT_end[destination] += 1
        
    time_diff = datetime.now() - stamp_0
    print( " -> time:  %s[s]" % time_diff)
    print( " -> total: %s skipped: %s kept: %s" % (len(rows), skipped , len(rows) - skipped ))
    print( " -> unique origins: %s" % len(PT))

    return PT