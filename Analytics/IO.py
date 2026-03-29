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
        read_speed_mb_s = 50  # MB/s for modern SSD
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

def estimate_sqlite_load_time(filepath, selection=None, limit=0):
    """
    Estimate how long it will take to load the SQLite ODM file.
    
    Returns:
        dict with keys: 'estimated_seconds', 'estimated_string', 'total_rows', 'file_size_mb'
    """
    try:
        # Get file size
        file_size_bytes = os.path.getsize(filepath)
        file_size_mb = file_size_bytes / (1024 * 1024)
        
        # Quick connection to get row count
        conn = sqlite3.connect(filepath)
        cursor = conn.cursor()
        
        # Get total row count
        cursor.execute("SELECT COUNT(*) FROM OD")
        total_rows = cursor.fetchone()[0]
        
        # Get row count with filtering if applicable
        filtered_rows = total_rows
        if selection is not None and len(selection) > 0:
            placeholders = ",".join(["?"] * len(selection))
            query = f"SELECT COUNT(*) FROM OD WHERE origin IN ({placeholders})"
            cursor.execute(query, selection)
            filtered_rows = cursor.fetchone()[0]
            
            if limit > 0:
                query = f"SELECT COUNT(*) FROM OD WHERE origin IN ({placeholders}) AND distance < ?"
                cursor.execute(query, selection + [limit])
                filtered_rows = cursor.fetchone()[0]
        else:
            if limit > 0:
                cursor.execute("SELECT COUNT(*) FROM OD WHERE distance < ?", (limit,))
                filtered_rows = cursor.fetchone()[0]
        
        conn.close()
        
        # Estimate based on empirical measurements:
        # - SQLite sequential read on SSD: ~50 MB/s
        # - Per-row processing overhead: ~0.0001 seconds per row
        # - Total estimate = (file_size / read_speed) + (row_count * overhead)
        
        read_speed_mb_s = 50  # MB/s for modern SSD
        processing_overhead_per_row = 0.00005  # seconds
        
        # Time to read file
        file_read_time = file_size_mb / read_speed_mb_s
        
        # Time to process rows (parsing, string operations, dict insertions)
        processing_time = filtered_rows * processing_overhead_per_row
        
        # Add overhead for filtering/parsing
        if selection is not None or limit > 0:
            processing_time *= 1.2  # 20% penalty for filtering
        
        total_estimated_time = file_read_time + processing_time
        
        # Format as human-readable string
        if total_estimated_time < 1:
            time_string = f"{total_estimated_time*1000:.0f} ms"
        elif total_estimated_time < 60:
            time_string = f"{total_estimated_time:.1f}s"
        else:
            minutes = int(total_estimated_time // 60)
            seconds = int(total_estimated_time % 60)
            time_string = f"{minutes}m {seconds}s"
        
        return {
            'estimated_seconds': total_estimated_time,
            'estimated_string': time_string,
            'total_rows': total_rows,
            'filtered_rows': filtered_rows,
            'file_size_mb': file_size_mb,
            'file_read_time': file_read_time,
            'processing_time': processing_time
        }
        
    except Exception as e:
        print(f"Error estimating load time: {str(e)}")
        return {
            'estimated_seconds': 0,
            'estimated_string': "Unknown",
            'total_rows': 0,
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

def read_ODM( filepath, remove_prefix = True, origin_prefix_whitelist = [], destination_prefix_whitelist = [], max_duration = 0, bar = None, selection = None, limit=0 ):


    """
        
    RETURN:
        D[origin][destination] = (distance, duration)


    """

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

        D[origin][destination] = (distance, duration)

        # if "PT" in origin and "GRD" in destination:
        #     stat += 1

    time_diff = datetime.now() - stamp_0
    print( " -> time:  %s[s]" % time_diff)
    print( " -> total: %s skipped: %s kept: %s" % (len(rows), skipped , len(rows) - skipped ))

    if bar is not None:
        bar.setValue(len(rows))
        QCoreApplication.processEvents()

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
    

    return PT, PT_start, PT_end