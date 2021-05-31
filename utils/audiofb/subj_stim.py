from pynfb.helpers.simple_socket import SimpleServer
from pynfb.inlets.lsl_inlet import LSLInlet
from time import sleep
from psychopy import visual, core, sound
import numpy as np
from pynfb.signal_processing.filters import CFIRBandEnvelopeDetector, DownsampleFilter, SpatialFilter, IdentityFilter, ExponentialSmoother
from pynfb.outlets.signals_outlet import SignalsOutlet
from utils.audiofb.volume_controller import VolumeController

FS_OUT = 500

# init psychopy window
win = visual.Window(fullscr=False)
message = visual.TextStim(win, text='', alignHoriz='center')
message.autoDraw = True  # Automatically draw every frame
beep = sound.Sound('A')

# voice synthesizer https://cloud.yandex.ru/services/speechkit#demo
# ogg to wav 1 channel https://online-audio-converter.com/ru/
voices = {'close': sound.Sound('voice/close2.wav'),
          'open': sound.Sound('voice/open_eyes.wav'),
          'filters': sound.Sound('voice/filters.wav'),
          'baseline': sound.Sound('voice/baseline.wav'),
          'start': sound.Sound('voice/start.wav'),
          'pause': sound.Sound('voice/pause.wav')}

# connect to volume controller
message.text = 'Сообщение экспериментатору:\nПодключение к Arduino контроллеру громкости...'
win.flip()
volume_controller = VolumeController()
sleep(2)
volume_controller.set_volume(100)
sleep(1)
volume_controller.set_volume(0)


# connect to LSL inlet
message.text = 'Сообщение экспериментатору:\nПодключение к LSL потоку "NVX136_Data"...'
win.flip()
lsl_in = LSLInlet('NVX136_Data')
fs_in = int(lsl_in.get_frequency())
channels = lsl_in.get_channels_labels()

# create LSL outlet
lsl_out = SignalsOutlet(channels, fs=FS_OUT, name='NVX136_FB')

# connect to NFBLab
message.text = 'Сообщение экспериментатору:\nЗапустите эксперимент в NFBLab'
win.flip()
server = SimpleServer()

# setup filters
downsampler = DownsampleFilter(int(fs_in / FS_OUT), len(channels))
spatial_filter = np.zeros(len(channels))
spatial_filter[0] = 1
cfir = CFIRBandEnvelopeDetector([8, 12], FS_OUT, ExponentialSmoother(0.), n_taps=500)
mean = 0
std = 1

# init values
score = np.zeros(1)
play_feedback = False
while 1:
    # receive and process chunk
    chunk, timestamp = lsl_in.get_next_chunk()
    if chunk is not None:
        # down sampling
        chunk[:, -1] = np.abs(chunk[:, -1])
        chunk = downsampler.apply(chunk)

        # compute feedback score
        if len(chunk) > 0:
            virtual_channel = chunk.dot(spatial_filter)
            envelope = cfir.apply(virtual_channel)
            score = (envelope - mean)/(std if std > 0 else 1)

            if play_feedback:
                volume = (np.tanh(score[-1]) / 2 + 0.5) * 50 + 50
                # print(score, volume)
                volume_controller.set_volume(volume)

            # push down-sampled chunk to lsl outlet
            lsl_out.push_chunk(chunk.tolist())

    # handle NFBLab client messages
    meta_str, obj = server.pull_message()
    if meta_str is None:
        continue
    elif meta_str == 'msg':  # baseline blocks (set message and stop NFB)
        play_feedback = False
        volume_controller.set_volume(0)
        print('Dummy.. Set message to "{}"'.format(obj))
        message.text = obj
        if obj == 'Pause':
            voices['pause'].play()
        elif obj == 'Close':
            voices['close'].play()
        elif obj == 'Open':
            voices['open'].play()
        elif obj == 'Baseline':
            voices['baseline'].play()
        elif obj == 'Filters':
            voices['filters'].play()

        win.flip()
    elif meta_str == 'fb1':  # fb blocks
        voices['start'].play()
        play_feedback = True
        print('Dummy.. Run FB. Set message to "{}"'.format(obj))
        message.text = obj
        win.flip()
    elif meta_str == 'spt':  # update spatial filter
        spatial_filter = obj
        print('Dummy.. Set spatial filter to {}'.format(obj))
    elif meta_str == 'bnd':  # update bandpass filter
        cfir = CFIRBandEnvelopeDetector(obj, FS_OUT, ExponentialSmoother(0.), n_taps=500)
        print('Dummy.. Set band to {}'.format(obj))
    elif meta_str == 'std':  # update fb score stats
        mean, std = obj
        print('Dummy.. Set stats to {}'.format(obj))



