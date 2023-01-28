# ]\[-Vision v0.3

Streaming video and audio for the Apple II.

]\[-Vision transcodes video files in standard formats (.mp4 etc) into a custom format optimized for streaming playback on
Apple II hardware.

Requires:
- 64K 6502 Apple II machine (tested on //gs and //e but should also work on ]\[/]\[+)
- [Uthernet II](http://a2retrosystems.com/products.htm) ethernet card
  - AppleWin ([Windows](https://github.com/AppleWin/AppleWin) and [Linux](https://github.com/audetto/AppleWin)) and [Ample](https://github.com/ksherlock/ample) (Mac) emulate the Uthernet II.  ]\[-Vision has been confirmed to work with Ample.

Dedicated to the memory of [Bob Bishop](https://www.kansasfest.org/2014/11/remembering-bob-bishop/), early pioneer of Apple II
[video](https://www.youtube.com/watch?v=RiWE-aO-cyU) and [audio](http://www.faddensoftware.com/appletalker.png).

## In action

Sample videos (recording of playback on Apple //gs with RGB monitor, or HDMI via VidHD)

TODO: These are from older versions, for which quality was not as good.

Double Hi-Res:
- [Try getting this song out of your head](https://youtu.be/S7aNcyojoZI)
- [Babylon 5 title credits](https://youtu.be/PadKk8n1xY8)

Hi-Res:
- [Bad Apple](https://youtu.be/R5_af8Mo0Q4)

Older Hi-Res videos:
- [Paranoimia ft Max Headroom](https://youtu.be/wfdbEyP6v4o)
- [How many of us still feel about our Apple II's](https://youtu.be/-e5LRcnQF-A)

There may be more on this [YouTube playlist](https://www.youtube.com/playlist?list=PLoAt3SC_duBiIjqK8FBoDG_31nUPB8KBM)

## Details

The audio is a 5-bit DAC at 73 cycles/sample (~14.3KHz carrier), which is a well-known technique (going back to ~1990).  With 73 cycles/audio sample there are a lot of otherwise-wasted cycles in between the speaker ticks.  It turns out, there's enough space to multiplex streaming video data (writing 4 screen bytes per sample) 

This ends up streaming data at about 100KB/sec of which 56KB/sec are updates to the hires screen memory.  This is enough for about 8 full redraws of the hires graphics screen per second (i.e. if the entire screen contents change between frames).  If we didn't care about audio, one can get substantially more video throughput i.e. a higher quality video-only stream, but this seems to be a good sweet spot in terms of video + audio quality. 

The video frames are actually encoded at the original frame rate (or optionally by skipping frames), prioritizing differences in the screen content, so the effective frame rate is higher than this if only a fraction of the screen is changing between frames (which is the typical case). 

I'm using the excellent (though under-documented ;) [BMP2DHR](https://github.com/digarok/b2d) to encode the input video stream into a sequence of memory maps, then post-processing the frame deltas to prioritize the screen bytes to stream in order to approximate these deltas as closely as possible within the timing budget. 

### KansasFest 2019 presentation

I gave a talk about this at [KansasFest 2019](https://www.kansasfest.org/), see the [slides](https://docs.google.com/presentation/d/1YhpMOoVjkXKm2iYAlpB-03HqnLHUsilsOW-83OHwZVE/edit?usp=sharing)

TODO: link video once it is available.

## Installation

This currently requires python3.8 because some dependencies (e.g. weighted-levenshtein) don't compile with 3.9+.

```
python3.8 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Before you can run the transcoder you need to generate the data files it requires:

```
% python transcoder/make_data_tables.py
```

This is a one-time setup.  It takes about 90 minutes on my machine.

## Sample videos

Some sample videos are available [here](https://www.dropbox.com/sh/kq2ej63smrzruwk/AADZSaqbNuTwAfnPWT6r9TJra?dl=0) for
streaming (see `server/server.py`)

## Release Notes

### v0.3 (17 Jan 2023)

- Fixed an image quality bug in the transcoder
- Documentation/quality of life improvements to installation process
- Stop using LFS to store the generated data files in git, they're using up all my quota

### v0.2 (19 July 2019)

#### Transcoder

- Support for Double Hi-Res playback
  - During slow-path processing, flip the MAIN/AUX soft switch for subsequent writes.  This introduces some horizontal interlacing that is sometimes visible, but quality is generally good.
  - Video now has a header to select playback mode, plus 6 padding bytes that are currently unused
- Improved video quality
  - Reimplemented the colour model, now aware of NTSC artifact colours, fringing, interference.
    - Uses a 4-bit sliding window over the display bitstream to model the NTSC colours, which is a discrete approximation to the (continuous) NTSC colour signal
    - Use CIE2000 colour distance to model perceptual distance between colour values.
  - Add a --palette argument for selecting between NTSC and //GS RGB palettes.
  - Fix an off-by-one in video frame counting that was causing audio and video to become desynchronized
- Improved audio quality
  - Encode at 14.7KHz instead of 14.3Khz, which is an integral divisor of 44.1KHz (the most common audio bitrate).
    - This gives better audio quality and is faster to encode, while only changing playback speed by <3%.
  - Add --audio_bitrate argument to allow for custom playback speeds.
    - For //gs at 2.8MHz 22500 is a good value (happily, another integral divisor of 44.1KHz, and also within 3% of the "correct" value).  Playback is only about 1.6x faster at 2.8MHz, probably because access to I/O page is still clocked at 1MHz.
- Other internal changes:
  - Introduces a uniform model for HGR and DHGR bitmap graphics, with colour modulation
  - Screen bitmaps are efficiently represented in a format that allows precomputing all
    of the possible edit distances between source and target bytes (including the colour effect on neighbouring bytes due to the 4-bit sliding window)
      - Downside is this takes longer to start up since the edit distance matrix needs to be loaded at first use, which can take 1-2m.

#### Player
- Support for Double Hi-Res playback
- Press any key to pause/resume
- Improved playback audio quality
  - Optimized the slow-path from 3x73 to 2x73 cycles
  - Use 34-cycle duty cycle for speaker, not 36 (34 is the "baseline" duty cycle i.e. normalized as the zero-value of the input PCM stream)

### v0.1 (23 March 2019)

- Initial release

## Internals

### Organization

player/
- Apple II video player.  This is the timing-critical part.

server/
- Simple python program that listens on port 1977 and streams out a given file upon connection.

simulator/
- Python-based 6502 simulator that implements enough of the Apple II and Uthernet II to (in theory) test the player.  Currently incomplete - e.g. TCP/socket buffer management is not implemented yet.  In theory this would be useful for e.g. debugging, validating timings, etc, but I didn't end up needing to go this far yet.

transcoder/
- Python-based video transcoder, which multiplexes audio and video streams into a stream of player opcodes.  This is where most of the algorithmic complexity happens.  It is fairly optimized (e.g. using numpy to vectorize array operations etc) but is not especially efficient and currently something like 5x-10x slower than real-time.  

## Implementation

This project got started after I bought an Uthernet II and was looking for something interesting to do with it :)   Something caught my eye when I was reading the manual - the W5100 has 16K of onboard memory for TCP send/receive buffers, and the Apple II interface is via an I/O address that auto-increments the address pointer on the W5100.  This means that iterating through the received TCP data is very cheap on the Apple side if all you care about is reading in sequence. 

Actually this is the fastest possible way for the 6502 to read data (without DMA) since we’re just reading a single memory address repeatedly, and we can read up to 8k at a time this way before we have to deal with socket buffer management. 

### Player

In implementing video+audio playback I arrived at a couple of key principles:

1. audio requires cycle-exact timing control of when to tick the speaker, which pretty much means that all possible operations of the player must have constant time (or at least multiples thereof) 

1. you can’t afford to waste cycles on conditional operations, e.g. the player figuring out what a byte means or what to do next.  Conditional operations mess with the audio timings, and more importantly at 1MHz we don’t have cycles to waste on such luxuries. 

In fact in the inner playback loop there are no conditional 6502 opcodes at all, except for the slow-path where I have to manage the TCP stream, which is non-deterministic in one aspect (new data may not have arrived yet).  Otherwise the 6502 is fully steered by the byte stream - not just video data but also decoder addresses to JMP to next, and when the socket buffer needs to be managed.  This is how I select which speaker duty cycle to select next, as well as which hires screen page to store data on during that audio frame.  It turns out to (barely) fit together with ProDOS in 64k. 

The player is structured in terms of discrete opcodes, which each read 0 or more bytes from the TCP buffer as arguments, and then read a 2-byte address from the TCP buffer that is used to vector to the next opcode.

We use a 73-cycle fundamental period, i.e. all video/audio decoding opcodes take 73 cycles, and the "slow path" TCP buffer management takes 2x73 cycles (so as to minimize disruption to audio).  This gives 14364 Hz as the "carrier" frequency of the audio modulation, which is high enough to not be too audible when played back through the builtin speaker (at least to my ageing ears!).  Note that playing back through an external speaker will probably have a better high-frequency response, i.e. the carrier may be more audible.

Playback is driven by "fat" opcodes that combine a single 14364Hz audio cycle with 4 stores to display memory.  These opcodes are parametrized by:
- the memory page on which to write (page 0x20 .. 0x3f, i.e. hires screen page 1)
- the number of clock cycles for which the speaker should be driven (4 .. 66 cycles in steps of 2, i.e. 32 gradations)
  - 2 of these 32 duty cycles are off by one clock cycle because I couldn't find a way to exactly reproduce the target cycle count

i.e. there are 32 * 32 = 1024 variants of these opcodes, which end up taking up the majority of free memory.

Each of these opcodes does the following:
- actuates the speaker for the desired number of clock cycles
- reads a content byte from the TCP stream
- reads 4 offset bytes from the TCP stream and stores the content byte at these offsets for the opcode's memory page.

Management of the socket buffer + TCP stream is also scheduled by an "ACK" opcode placed at 2KB boundaries in the stream, which is a "slow path" where we temporarily fall out of the video/audio stream processing.  This avoids the need for the player to explicitly manage the buffering (e.g. when to ACK) as well as simplifying the buffer management logic.

During this ACK opcode we also read a TCP stream byte and self-modify to use it as a $C0xx address to store, i.e. flipping a soft-switch.  This allows us to steer screen writes between MAIN and AUX screen memory during DHGR video decoding.
During slow path we need to make sure to maintain a 34-cycle speaker duty cycle, and align to multiples of 73 cycles to minimize audio disruption.  Currently this fits in 2x73 cycles.

### Transcoder

The player code is somewhat intricate but "dumb" in the sense of being highly optimized for placing bytes into screen memory (while controlling the speaker duty cycle) without regard for their meaning.  The transcoder is responsible for quality of the video and audio stream, i.e. this is where the "heavy lifting" happens.

Audio processing is relatively straightforward and consists of:
- resampling the input audio stream to the target frequency of the player
  - actually we choose a nearby frequency (14.7KHz instead of 14.3KHz), which is within 3% of the true value and gives better audio quality since it's an integral divisor of the input audio rate (44.1KHz)
- estimating a normalization factor to rescale the audio amplitudes to cover the full range (since many audio streams are not well normalized)

Video processing requires more work, because it is highly constrained:
- by bandwidth: we cannot transmit every byte necessary to render frames at a reasonable frame rate (e.g. 15 fps)
- by the structure of the player opcodes that store a single content byte at 4 offsets on a given memory page.

i.e. it is necessary to prioritize which screen bytes to send to maximize the perceived image quality, and also to introduce controlled errors (e.g. deciding when it is worthwhile to store a content byte at some offset, that is not the exact content byte that we want but which does not introduce too much visual error)

TODO: describe this algorithm in more detail

## Known issues

### Crashing on cold boot

For some reason the player often crashes on cold-boot :(  Something must not be getting initialized properly.

### Configuration

The video player currently has hard-coded configuration (i.e. not configurable at runtime) in several ways:

- source and destination IP addresses are fixed
- assumes the Uthernet II is in slot 1.

Supporting configurable IP addresses should be relatively straightforward to implement, but configuring the slot requires patching many addresses in the player binary and would take additional effort.

For now you'll need to build this yourself.  The makefile in the player/ directory uses the excellent [Apple2BuildPipeline](https://github.com/jeremysrand/Apple2BuildPipeline) from Jeremy S. Rand, which requires Mac OS X.

### Tight coupling of player and video format

Because the transcoder effectively compiles the video for a particular version of the player (by reading the symbol table and emitting player opcode addresses into the byte stream), this means that any changes to these symbol offsets will mean the player is unable to play back existing videos (and will likely crash, hang etc when JMPing to a random offset)

## Future improvements

### Video quality improvements

#### Global optimization

The current approach to minimizing error uses a "greedy" algorithm of picking the single highest-value (page, offset) to store, then looking for 3 more offsets whose error will be maximally reduced.  This is faster to compute but may not be globally optimal, e.g. the best value to store to minimize the total error of 4 offsets may not even be any one of those target content bytes (e.g. some intermediate value)
Directly solving the joint optimization problem of picking the best (content, page, offsets) should give a higher fidelity video stream, at the cost of being more CPU-intensive to encode.

#### Direct image encoding

The current approach of first producing a "ground truth" memory representation of the image (using BMP2DHR) and then trying to minimize deltas from the current memory frame, is effectively an approximation of an approximation of the true image.  e.g. BMP2DHR does not seem to be aware of NTSC artifact colours, and may have a lower image quality than ideal.

Also, since our image-formation constraints are novel (storing 4 random byte offsets at once), we may be able to perform error diffusion in a way that is better adapted to this scheme.

### Mono playback mode

Adding video support optimized for playback on monochrome monitors should be straightforward, since the underlying dot model is already implemented.

### Looser coupling between player and transcoder version.

It should be possible to at least detect a mismatched player and transcoder version by maintaining a player version number and including this in a video header.

The video transcoder should be able to detect when the symbol addresses have changed (e.g. by maintaining a cache of versions and symbol addresses) and require the version to be incremented.

With a version cache the video server could also translate on the fly by interpreting the byte stream and mapping old offsets to the appropriate values for the current player version.


### Interactive video selection

Currently the player will attempt to connect to the server and stream whatever video is offered.  It would be possible to implement interactive selection of the video file to play.

### Playback controls

Seeking in the stream would require more work (since currently there is no communication in the Apple II --> server direction).  Also since the encoding is not real-time, this would either require significant optimization (perhaps rewriting at least the critical path of the encoder in C), or living with the resulting "video tearing" that would result from switching to a random place in the video stream.

