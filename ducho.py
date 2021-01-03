#!/usr/bin/env python3

import os, sys, datetime, random, json, haversine

try:
    import ijson
except ImportError:
  print(f"ijson not installed - please run 'pip install ijson' and rerun.")
  sys.exit(1)

randseed=int(os.environ.get("RANDSEED", datetime.datetime.now().microsecond))
random.seed(randseed)

dbg=(int(os.environ.get("DBG", 0)) != 0)

max_tsdiff_secs = float(os.environ.get("MAX_TS_DIFF", "1000"))  # secs
max_dist_km = float(os.environ.get("MAX_DIST_KM", "0.5"))  # km

mints = int(os.environ.get("MINTS", "1294097317")) # approx dec 30, 2010
maxts = int(os.environ.get("MAXTS", "2000000000")) # end of time
if mints < 0:
    print(f"MINTS must be greater than zero.")
    sys.exit(1)
if maxts <= mints:
    print(f"MINTS must be before MAXTS.")
    sys.exit(1)


def parseFile(filename):
    res = []
    placeVisits = ijson.items(open(filename), "timelineObjects.item")
    #print(len([i for i in placeVisits]))
    for placeVisit in placeVisits:
        if 'placeVisit' not in placeVisit:
            continue
        if 'location' not in placeVisit['placeVisit']:
            continue
        loc = placeVisit['placeVisit']['location']
        if "longitudeE7" not in loc or "latitudeE7" not in loc:
            continue
        if "duration" not in placeVisit['placeVisit']:
            continue
        dur = placeVisit['placeVisit']['duration']
        if "startTimestampMs" not in dur:
            continue
        # Fix overflows in Google Takeout data:
        # https://gis.stackexchange.com/questions/318918/latitude-and-longitude-values-in-google-takeout-location-history-data-sometimes
        lat = int(loc["latitudeE7"])
        lat = lat - 4294967296 if lat > 1800000000 else lat
        lon = int(loc["longitudeE7"])
        lon = lon - 4294967296 if lon > 1800000000 else lon
        res.append([ int(float(dur["startTimestampMs"]) / 1000), lat/10000000.0, lon/10000000.0 ])
        if dbg and len(res) % 100 == 0: print(".", end="", flush=True)
        if dbg: print("")
    return res

  
# mode to generate some data, run with GENERATE=1000 ./ducho.py to generate 1000 records
gen = int(os.environ.get("GENERATE", "0"))
if gen > 0:
    minlat = int(os.environ.get("MINLAT", "407226780")) # queensish
    maxlat = int(os.environ.get("MAXLAT", "407546850")) # new jerseyish
    minlon = int(os.environ.get("MINLON", "-742452120")) # staten island
    maxlon = int(os.environ.get("MAXLON", "-739111950")) # westchesterish
    locs = []

    def genPlace(ts, lat, lon):
        return {'placeVisit': {'duration': {"startTimestampMs": str(int(ts))}, 'location':{ "latitudeE7": lat, "longitudeE7": lon} }}

    # if a filename is provided, we treat them as source data to be matched
    # i.e. so you can then compare this file to the output of that file
    if len(sys.argv) == 2:
        items = [i for i in parseFile(sys.argv[1])]
        overlaps = min(len(items), int(os.environ.get("OVERLAPS", "100")), gen)
        print(f"generate {gen} with {overlaps} overlaps, out of {len(items)} items from the original dataset", file=sys.stderr)
        for item in random.choices(items, k=overlaps):
            ts = int(item[0] + random.random()*max_tsdiff_secs*2 - max_tsdiff_secs)
            latdiff = max_dist_km / 100.0
            lat = item[1] + random.random()*latdiff*2 - latdiff
            lon = item[2]
            locs.append(genPlace(ts*1000, int(lat*10000000), int(lon*10000000)))
            print(f"ts: {item[0]} => {ts} ({item[0]-ts:+d} secs)  lat: {item[1]:.3f} => {lat:.3f}  lon: {lon}", file=sys.stderr)
        gen = max(0, gen - overlaps)
        
    for i in range(gen):
        ts = int(random.random() * (maxts - mints) + mints) * 1000
        lat = int(random.random() * (maxlat - minlat) + minlat)
        lon = int(random.random() * (maxlon - minlon) + minlon)
        locs.append(genPlace(ts, lat, lon))
    locs = sorted(locs, key=lambda rec: rec['placeVisit']["duration"]["startTimestampMs"])
    json.dump({"timelineObjects": locs}, sys.stdout)
    sys.exit(0)

if len(sys.argv) != 3:
    print(f"Usage: {sys.argv[0]} <takeout file1> <takeout file1>", file=sys.stderr)
    sys.exit(1)

locs1 = sorted(parseFile(sys.argv[1]), key=lambda rec: rec[0])
locs2 = sorted(parseFile(sys.argv[2]), key=lambda rec: rec[0])
if len(locs1) == 0:
    print(f"didn't find any location-items in file1", file=sys.stderr)
    sys.exit(1)
if len(locs2) == 0:
    print(f"didn't find any location-items in file2", file=sys.stderr)
    sys.exit(1)

def avg(x,y):
    return (x+y)/2.0

# TODO(perf): O(n^2) algorithm if items in both lists are dense-by-time.
# one easy optimization is to compress geo-near items from a given list into fewer records
# (extreme example: pandemic quarantine = lots of pings from the couch)

i1 = i2 = 0
while i1 < len(locs1):
    # check time
  old_i1=i1
  old_i2=i2
  while i1<len(locs1) and i2<len(locs2):  # easier to put the check up here
      loc1 = locs1[i1]
      loc2 = locs2[i2]
      ts1 = loc1[0]
      ts2 = loc2[0]
      if abs(ts1 - ts2) >= max_tsdiff_secs:
          break
      if dbg: print(f"i1={i1:5d},i2={i2:5d}  near in time: diff={abs(ts1 - ts2):6.0f} ts1={ts1:.0f} ts2={ts2:.0f}", end="")
      # check distance
      dist = haversine.haversine( loc1[1:], loc2[1:])
      if dbg: print(f"  dist={dist:6.3f}")
      if dist < max_dist_km:
          print(f"==> colocated!  tsdiff: {abs(ts1 - ts2):6.0f} secs   dist: {dist:2.2f} km  "
                f"roughly {datetime.datetime.fromtimestamp(avg(ts1,ts2)).strftime('%Y-%m-%d %H:%M')} @ "
                f"{avg(loc1[1],loc2[1]):3.4f},{avg(loc1[2],loc2[2]):3.4f} - ts1={ts1}")
          # advance the younger of the counters
      if ts1 > ts2 or i2 == len(locs2)-1:
          if dbg: print(f"  advancing i1 until ts diff >= {max_tsdiff_secs}")
          i1 += 1
      elif i1 == len(locs1)-1:
          break
      else:
          if dbg: print(f"  advancing i2 until ts diff >= {max_tsdiff_secs}")
          i2 += 1
    
  i1 = old_i1
  i2 = old_i2
  # advance the older of the counters
  if dbg: print(f"ts1={ts1:.0f} ts2={ts2:.0f} diff={abs(ts1 - ts2):6.0f} i1={i1} i2={i2}... ", end="", flush=True)
  if ts1 < ts2 or i2 == len(locs2)-1:
      if dbg: print(f"advancing i1.")
      i1 += 1
      continue
  i2 += 1
  if dbg: print(f"advancing i2.")


