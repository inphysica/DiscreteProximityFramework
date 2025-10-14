import sqlite3
import json
from datetime import datetime, timedelta
import os

# from tqdm import tqdm

import sys


from qgis.PyQt.QtWidgets import QDialog, QPushButton, QLineEdit, QFileDialog, QMessageBox, QProgressBar
from qgis.PyQt.QtCore import QCoreApplication


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
