'''*-----------------------------------------------------------------------*---
                                                          Author: Jason Ma
                                                          Date  : May 22 2017

    File Name  : top_level_bladeRF.py
    Description: Used for either transmitting or receiving data using the
                 appropriate GNURadio modules and a BladeRF board. 
                 
             .-------------top_level_bladeRF-----------.
            /     /           |             \           \
rx_processor   scanner   blade_rx   gnuradio_interface  .--------------------.
                                             |          | Additional Sensors |
                      .--------------------------.      |                    |
                      | GNURadio Generated Files |      | hardware           |
                      |                          |      |____________________|
                      | ofdm_transmitter         |         
                      | ofdm_receiver            |
                      |__________________________| 

- top_level_bladeRF loads the FPGA onto the BladeRF using blade_rx. It then 
  starts and maintains all the other threads:
  - gnuradio_interface
  - rx_processor
  - scanner
  - hardware
  It allows for smooth handling of exits (including Ctrl+C).

- gnuradio_interface calls rx or tx GNURadio schemes depending on configuration
  to either receive or transmit data using whatever modulation scheme has been
  implemented. The idea behind this file is to make it modular, being capable of 
  calling any gnuradio generated files that write to the appropriate file and 
  implement the main call.

- rx_processor processes the data received, capable of accessing the bitstream 
  containing communication data, GPS, and anything else being collected. This 
  can be set to work on old or new data.

- scanner has peak detection and RSSI measuring capability.

- hardware interfaces with the air quality sensor, modified slightly from 
  Michael / Christine's code to work with top level's callbacks
---*-----------------------------------------------------------------------*'''

import blade_rx
import bladeRF_scanner
import gnuradio_interface

import sys
import time

'''----------------------------------------------------------------------------
Config variables
----------------------------------------------------------------------------'''

#top_level_bladeRF config
run_time = 10000

#center_freq = 433920000
center_freq = 440000000
bandwidth   = 1500000 #TODO currently NOT being used by gnuradio_interface effectively
baud_rate   = 50000 #TODO currently NOT being used by gnuradio_interface effectively

#gnuradio_interface parameters
tx = False
rx = True
tx_time = 10000
rx_time = 10000

#rx_processor parameters
rx_process = True
gps_tagging = False
pre_headers = ['SL1', 'SL2', 'SL3']
post_headers = ['EL4', 'EL5', 'EL6']
in_file  = 'io/_out'

#scanner parameters
scan = False
scan_best_freqs = False
section_bw = 50000
fft_size = 4096
fft_file = 'io/log_power_fft_data.bin'


#hardware parameters
air_sensor = False

'''----------------------------------------------------------------------------
Conditional imports and settings
----------------------------------------------------------------------------'''

if air_sensor:
  import hardware

if rx_process:
  import rx_processor

if len(sys.argv) < 3:
  print("Usage: python top_level_bladeRF [f | tx | rx | rxnp | p | m] <freq>\n \
        \tf    - full duplex (both tx and rx)\n \
        \ttx   - transmit new samples\n \
        \trx   - receive new samples\n \
        \trxnp - receive, but do not process samples\n \
        \tp    - process pre-received samples from in_file\n \
        \tm    - manual selection\n \
        freq   - frequency to start at")
  sys.exit(1)

if sys.argv[1] == 'f': #full duplex
  print '[main] Mode: Full Duplex'
  tx = True
  rx = True
  rx_process = True
elif sys.argv[1] == 'tx': #tx only
  print '[main] Mode: TX'
  tx = True
  rx = False
  rx_process = False
elif sys.argv[1] == 'rx': #rx only
  print '[main] Mode: RX'
  tx = False
  rx = True
  rx_process = True
elif sys.argv[1] == 'rxnp': #rx samples without processing
  print '[main] Mode: RX without processing'
  tx = False
  rx = True
  rx_process = False
elif sys.argv[1] == 'p': #process only
  print '[main] Mode: Processing only'
  tx = False
  rx = False
  rx_process = True
elif sys.argv[1] == 'm': #manual mode
  print '[main] Mode: Manual'
else: #invalid input
  print("Usage: python top_level_bladeRF [f | tx | rx | rxnp | p | m] <freq>\n \
        \tf    - full duplex (both tx and rx)\n \
        \ttx   - transmit new samples\n \
        \trx   - receive new samples\n \
        \trxnp - receive, but do not process samples\n \
        \tp    - process pre-received samples from in_file\n \
        \tm    - manual selection\n \
        freq   - frequency to start at")
  sys.exit(1)

if sys.argv[2] < 300 or sys.argv[2] > 3800:
  print("Frequency cannot be < 300MHz or > 3.8GHz")
  sys.exit(1)

'''[end_all_threads]-----------------------------------------------------------
  Sends an end_callback to all threads in thread list
----------------------------------------------------------------------------'''
def end_all_threads(threads):
  print '[main] Ending program.'

  for thread in threads:
    thread.end_callback()

  sys.exit(1)

'''[main]----------------------------------------------------------------------
  Initializes gnuradio_interface and bladeRF_scanner threads, which handle
  data collection and processing independently.
----------------------------------------------------------------------------'''
def main():

  global center_freq

  try:
    #init threads
    print '[main] Tx:\t' + str(tx)
    print '[main] Rx:\t' + str(rx)
    print '[main] Rx_proc:\t' + str(rx_process)
    print '[main] Scanner:\t' + str(scan)
    print '[main] Aq_sen:\t' + str(air_sensor)
    print '\n'

    threads = []
    filewrite_subscribers = []

    #loads fpga
    if tx or rx:
      print '[main] Initializing bladeRF'
      sdr = blade_rx.blade_rf_sdr(1)

      print '[main] Initializing GNURadio interface'
      gr = gnuradio_interface.gr_thread(tx, rx, tx_time, rx_time, center_freq, bandwidth, baud_rate)
    
    if scan:
      print '[main] Initializing scanner'
      scanner = bladeRF_scanner.bladeRF_scanner(fft_file, center_freq, bandwidth, section_bw, fft_size)

    if rx_process:
      print '[main] Initializing rx processor'
      rx_p = rx_processor.rx_processor(in_file, pre_headers, post_headers, rx, gps_tagging)

    if air_sensor:
      print '[main] Initializing hardware'
      air_q_s = hardware.AirSensor()

    #get list of best frequencies
    if scan_best_freqs:
      #best_freqs = bladeRF_scanner.main()
      #TODO need to fix above line, main is deprecated
      best_freqs = scanner.select_usable_by_section()

      #take lowest interference frequency and set it to center_freq for now
      center_freq = best_freqs[0]

      #do something with it

    if tx or rx:
      gr.start()
      threads.append(gr)

    if scan:
      scanner.start()
      threads.append(scanner)
      filewrite_subscribers.append(scanner)

    if rx_process:
      rx_p.start()
      threads.append(rx_p)
      filewrite_subscribers.append(rx_p)

    #if air_sensor:
    #  air_q_s.start()
    #  threads.append(air_q_s)
    #  filewrite_subscribers.append(air_q_s)

    start_time = time.time()
    while time.time() - start_time < run_time:

      wait_start = time.time()
      while(time.time() - wait_start < 1):
        time.sleep(0.1)

      print '\n[main] sending filewrite sync'

      for thread in filewrite_subscribers:
        thread.filewrite_callback()
      
  except KeyboardInterrupt:
    print '\n[main] Ctrl+c received.'
    end_all_threads(threads)

  print '\n[main] Time reached.'
  end_all_threads()

if __name__ == '__main__':
  main()
