// lib/audio_player_widget.dart
import 'package:flutter/material.dart';
import 'package:just_audio/just_audio.dart';
import 'dart:async';
import '../models/app_colors.dart'; // Import AppColors

class AudioPlayerWidget extends StatefulWidget {
  final String audioUrl;
  final bool isLocalFile;

  const AudioPlayerWidget({Key? key, required this.audioUrl, this.isLocalFile = false}) : super(key: key);

  @override
  State<AudioPlayerWidget> createState() => _AudioPlayerWidgetState();
}

class _AudioPlayerWidgetState extends State<AudioPlayerWidget> {
  final AudioPlayer _audioPlayer = AudioPlayer();
  PlayerState? _playerState;
  Duration? _duration;
  Duration? _position;
  StreamSubscription<PlayerState>? _playerStateSubscription;
  StreamSubscription<Duration?>? _durationSubscription;
  StreamSubscription<Duration?>? _positionSubscription;

  @override
  void initState() {
    super.initState();
    _initAudioPlayer();
  }

  Future<void> _initAudioPlayer() async {
    try {
      if (widget.isLocalFile) {
        await _audioPlayer.setFilePath(widget.audioUrl);
      } else {
        await _audioPlayer.setUrl(widget.audioUrl);
      }
      // await _audioPlayer.setUrl(widget.audioUrl);
      _playerStateSubscription = _audioPlayer.playerStateStream.listen((
        playerState,
      ) {
        if (mounted) {
          setState(() {
            _playerState = playerState;
          });
        }
      });
      _durationSubscription = _audioPlayer.durationStream.listen((duration) {
        if (mounted) {
          setState(() {
            _duration = duration;
          });
        }
      });
      _positionSubscription = _audioPlayer.positionStream.listen((position) {
        if (mounted) {
          setState(() {
            _position = position;
          });
        }
      });
    } catch (e) {
      debugPrint("Error loading audio: $e");
      // Consider showing an error message to the user
    }
  }

  @override
  void dispose() {
    _playerStateSubscription?.cancel();
    _durationSubscription?.cancel();
    _positionSubscription?.cancel();
    _audioPlayer.dispose();
    super.dispose();
  }

  String _formatDuration(Duration? duration) {
    if (duration == null) return '00:00';
    String twoDigits(int n) => n.toString().padLeft(2, '0');
    final minutes = twoDigits(duration.inMinutes.remainder(60));
    final seconds = twoDigits(duration.inSeconds.remainder(60));
    return '$minutes:$seconds';
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Padding(
          padding: const EdgeInsets.all(8.0),
          child: Text(
            'Audio Guide',
            style: Theme.of(
              context,
            ).textTheme.headlineSmall?.copyWith(color: AppColors.textPrimary),
          ),
        ),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            IconButton(
              icon: Icon(
                _playerState?.playing == true
                    ? Icons.pause_circle_filled
                    : Icons.play_circle_filled,
                color: AppColors.primary,
                size: 50,
              ),
              onPressed: () {
                if (_playerState?.playing == true) {
                  _audioPlayer.pause();
                } else {
                  _audioPlayer.play();
                }
              },
            ),
            Expanded(
              child: Slider(
                min: 0.0,
                max: _duration?.inMilliseconds.toDouble() ?? 0.0,
                value: _position?.inMilliseconds.toDouble() ?? 0.0,
                onChanged: (value) {
                  _audioPlayer.seek(Duration(milliseconds: value.toInt()));
                },
                activeColor: AppColors.primary,
                inactiveColor: AppColors.divider,
              ),
            ),
            Text(
              '${_formatDuration(_position)} / ${_formatDuration(_duration)}',
              style: const TextStyle(
                color: AppColors.textPrimary,
                fontSize: 14,
              ),
            ),
          ],
        ),
      ],
    );
  }
}
