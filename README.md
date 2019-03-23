# ][-Vision v0.1

Streaming video and audio for the Apple II.

][-Vision transcodes video files in standard formats (.mp4 etc) into a custom format optimized for streaming playback on
Apple II hardware.

Requires:
- 64K 6502 Apple II machine (only tested on //gs so far, but should work on older systems)
- [Uthernet II](http://a2retrosystems.com/products.htm) ethernet card
  - AFAIK no emulators support this hardware so you'll need to run it on a real machine to see it in action

Dedicated to the memory of [Bob Bishop](https://www.kansasfest.org/2014/11/remembering-bob-bishop/), early pioneer of Apple II
[video](https://www.youtube.com/watch?v=RiWE-aO-cyU) and [audio](http://www.faddensoftware.com/appletalker.png).

## Details

The audio is a 5-bit DAC at 73 cycles/sample (~14.3KHz carrier), which is a well-known technique.  With 73 cycles/audio sample there are a lot of otherwise-wasted cycles in between the speaker ticks.  It turns out, there's enough space to multiplex streaming video data (writing 4 screen bytes per sample) 

This ends up streaming data at about 100KB/sec of which 56KB/sec are updates to the hires screen memory.  This is enough for about 8 full redraws of the hires graphics screen per second (i.e. if the entire screen contents change between frames).  If we didn't care about audio, one can get substantially more video throughput i.e. a higher quality video-only stream, but this seems to be a good sweet spot in terms of video + audio quality. 

The video frames are actually encoded at the original frame rate, prioritizing differences in the screen content, so the effective frame rate is higher than this if only a fraction of the screen is changing between frames (which is the typical case). 

I'm using the excellent (though under-documented ;) [BMP2DHR](http://www.appleoldies.ca/bmp2dhr/) to encode the input video stream into a sequence of memory maps, then post-processing the frame deltas to prioritize the screen bytes to stream in order to approximate these deltas as closely as possible within the timing budget. 

### In action

Sample videos (recording of playback on Apple //gs)

- [Bad Apple](https://youtu.be/4JEChnZIrCw)
- [Try getting this song out of your head](https://youtu.be/WzE-pROpJ2o)
- [How many of us still feel about our Apple II's](https://youtu.be/-e5LRcnQF-A)

(The last two are from an older version, for which quality was not as good)

### Organization

player/
- Apple II video player.  This is the timing-critical part.

server/
- Simple python program that listens on port 1977 and streams out a given file upon connection.

simulator/
- Python-based 6502 simulator that implements enough of the Apple II and Uthernet II to (in theory) test the player.  Currently incomplete - e.g. TCP/socket buffer management is not implemented yet.  In theory this would be useful for e.g. debugging, validating timings, etc, but I didn't end up needing to go this far yet.

transcoder/
- Python-based video transcoder, which multiplexes audio and video streams into a stream of player opcodes.  This is where most of the algorithmic complexity happens.  It is somewhat optimized (e.g. using numpy to vectorize array operations etc) but is not especially efficient and currently something like 10x slower than real-time.  

## Implementation

This project got started after I bought an Uthernet II and was looking for something interesting to do with it :)   Something caught my eye when I was reading the manual - the W5100 has 16K of onboard memory for TCP send/receive buffers, and the Apple II interface is via an I/O address that auto-increments the address pointer on the W5100.  This means that iterating through the received TCP data is very cheap on the Apple side if all you care about is reading in sequence. 

Actually this is the fastest possible way for the 6502 to read data (without DMA) since we’re just reading a single memory address repeatedly, and we can read up to 8k at a time this way before we have to deal with socket buffer management. 

### Player

In implementing video+audio playback I arrived at a couple of key principles:

1. audio requires cycle-exact timing control of when to tick the speaker, which pretty much means that all possible operations of the decoder must have constant time (or at least multiples thereof) 

1. you can’t afford to waste cycles on conditional operations, e.g. the decoder figuring out what a byte means or what to do next.  Conditional operations mess with the audio timings, and more importantly at 1MHz we don’t have cycles to waste on such luxuries. 

In fact in the inner playback loop there are no conditional 6502 opcodes at all, except for the slow-path where I have to manage the TCP stream, which is non-deterministic in one aspect (new data may not have arrived yet).  Otherwise the 6502 is fully steered by the byte stream - not just video data but also decoder addresses to JMP to next, and when the socket buffer needs to be managed.  This is how I select which speaker duty cycle to select next, as well as which hires screen page to store data on during that audio frame.  It turns out to (barely) fit together with ProDOS in 64k. 

The player is structured in terms of discrete opcodes, which each read 0 or more bytes from the TCP buffer as arguments,
and then read a 2-byte address from the TCP buffer that is used to vector to the next opcode.

We use a 73-cycle fundamental period, i.e. all video/audio decoding opcodes take 73 cycles, and the "slow path" TCP buffer management takes 3x73 cycles (so as to minimize disruption to audio).  This gives 14364 Hz as the "carrier" frequency of the audio modulation, which is high enough to not be too audible (at least to my ageing ears!) 

Playback is driven by "fat" opcodes that combine a single 14364Hz audio cycle with 4 stores to display memory.

Management of the socket buffer + TCP stream is also scheduled by an "ACK" opcode placed at 2k boundaries in the stream.  This
avoids the need for the player to explicitly manage the buffering (e.g. when to ACK) as well as simplifying the buffer management logic.

### Transcoder

The player code is somewhat intricate but "dumb" in the sense of being highly optimized for placing bytes into screen memory (while controlling the speaker duty cycle) without regard for their meaning.  The transcoder is responsible for quality of the video and audio stream, i.e. this is where the "heavy lifting" happens.

Audio processing is relatively straightforward and consists of:
- resampling the input audio stream to the target frequency of the player
- estimating a normalization factor to rescale the audio amplitudes to cover the full range (since many audio streams are not well normalized)

Video processing requires more work, because it is constrained:
- by bandwidth: we cannot transmit every byte necessary to render frames at a reasonable frame rate (e.g. 15 fps)
- by the structure of the player opcodes that store a single content byte at 4 offsets on a given memory page.

i.e. it is necessary to prioritize which screen bytes to send to maximize the perceived image quality, and also to introduce controlled errors (e.g. deciding when it is worthwhile to store a content byte at some offset, that is not the exact content byte that we want but which does not introduce too much visual error)

## Known issues

### Configuration

The video player currently has hard-coded configuration (i.e. not configurable at runtime) in several ways:

- source and destination IP addresses are fixed
- assumes the Uthernet II is in slot 1.

Supporting configurable IP addresses should be relatively straightforward to implement, but configuring the
slot requires patching many addresses in the player binary and would take additional effort.

For now you'll need to build this yourself.  The makefile in the player/ directory uses the excellent
[Apple2BuildPipeline](https://github.com/jeremysrand/Apple2BuildPipeline) from Jeremy S. Rand, which requires Mac OS X.

### Tight coupling of player and video format

Because the transcoder effectively compiles the video for a particular version of the player (by reading the symbol table and
emitting player opcode offsets into the byte stream), this means that any changes to these symbol offsets will mean the player is unable to play back existing videos (and will likely crash, hang etc when JMPing to a random offset)

It should be possible to at least detect this situation by maintaining a player version number and including this in a video
header.

The video transcoder should be able to detect when the symbol addresses have changed (e.g. by maintaining a cache of versions and symbol addresses) and require the version to be incremented.

With a version cache the video server could also translate on the fly by interpreting the byte stream and mapping old offsets to the appropriate values for the current player version.

## Future improvements

### Double hi-res support

In principle it should be straightforward for the player to support double hi-res graphics, since this just requires toggling
the appropriate soft switches to enable writes to be steered onto MAIN or AUX screen memory.  This could be toggled in the ACK codepath.

The image encoder (BMP2DHGR) already supports this, so the only hard part is teaching the transcoder how to encode and sequence the video stream.

Of course, the effective frame rate will be halved so it remains to be seen how useful this will be in practise.

### Interactive video selection

Currently the player will attempt to connect to the server and stream whatever video is offered.  It would be possible to implement interactive video selection e.g. to allow 

### Colour model

Currently there is a half-hearted attempt to model some of the many interesting ways in which Apple II hires colours generate artefacts, but this is incomplete.  A more complete colour artefact model should increase the video quality (by allowing the encoder to be smarter when introducing errors)

### Playback controls

Adding support for pausing and resuming the playback should be relatively straightforward.  Seeking in the stream would require more work (since currently there is no communication in the Apple II --> server direction)

