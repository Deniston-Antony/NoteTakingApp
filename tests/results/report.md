# Test report — Kalman Filter & EKF lecture
*2026-10-27 19:38*

## Phase 1: file formats (3-minute clip)

| Format | Result | Words | Match vs reference | Time | Problems |
|---|---|---|---|---|---|
| audio mp3 | ✅ | 486 | 1.0 | 6.5 s |  |
| audio wav_16k_mono (like the 🎙 recorder) | ✅ | 471 | 1.0 | 5.7 s |  |
| audio wav_48k_stereo | ✅ | 473 | 1.0 | 6.2 s |  |
| audio m4a | ✅ | 618 | 1.0 | 9.1 s |  |
| audio ogg | ✅ | 485 | 0.99 | 6.2 s |  |
| audio opus | ✅ | 477 | 1.0 | 6.5 s |  |
| audio flac | ✅ | 471 | 1.0 | 6.4 s |  |
| audio webm | ✅ | 477 | 1.0 | 6.2 s |  |
| audio aac | ✅ | 489 | 1.0 | 6.3 s |  |
| audio wma | ✅ | 486 | 1.0 | 5.8 s |  |
| video mp4 | ✅ | 570 | 1.0 | 10.3 s |  |
| video mkv | ✅ | 486 | 0.99 | 6.4 s |  |
| video webm | ✅ | 486 | 0.99 | 7.2 s |  |
| video mov | ✅ | 613 | 1.0 | 9.3 s |  |
| video avi | ✅ | 488 | 0.99 | 6.0 s |  |

## Phase 2: input combinations (full 74-minute lecture)

| Run | Result | Time | Sections | Slides with speech | Estimate at 25% / 50% | Problems |
|---|---|---|---|---|---|---|
| pdf_only | ✅ | 15 min 33 s | 12 | 0/64 | 11 min 3 s / 11 min 11 s |  |
| youtube | ✅ | 14 min 0 s | 9 |  | 19 min 31 s / 16 min 24 s |  |
| youtube_pdf_code | ✅ | 22 min 53 s | 12 | 45/64 | 24 min 3 s / 20 min 50 s |  |
| youtube_whisper | ✅ | 19 min 55 s | 9 |  | 54 min 49 s / 27 min 3 s |  |
| audio_mp3 | ✅ | 12 min 21 s | 9 |  | 10 min 5 s / 11 min 18 s |  |
| audio_mp3_pdf | ✅ | 18 min 46 s | 12 | 41/64 | 15 min 4 s / 13 min 27 s |  |
| video_mp4 | ✅ | 11 min 37 s | 9 |  | 12 min 15 s / 9 min 45 s |  |
| video_mp4_pdf | ✅ | 20 min 44 s | 12 | 40/64 | 11 min 19 s / 18 min 52 s |  |
| record_pdf | ✅ | 16 min 13 s | 12 | 2/64 | 11 min 53 s / 11 min 51 s |  |
| pdf_only_no_vision | ✅ | 7 min 16 s | 12 | 0/64 | 14 min 19 s / 8 min 56 s |  |
