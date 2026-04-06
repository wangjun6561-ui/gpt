import 'package:audioplayers/audioplayers.dart';

class AudioService {
  AudioService._();

  static final AudioService instance = AudioService._();

  final AudioPlayer _fxPlayer = AudioPlayer();
  final AudioPlayer _tickPlayer = AudioPlayer();

  Future<void> preload() async {
    await _fxPlayer.setSource(AssetSource('sounds/complete.mp3'));
    await _tickPlayer.setSource(AssetSource('sounds/wheel_tick.mp3'));
  }

  Future<void> playComplete() async {
    await _fxPlayer.stop();
    await _fxPlayer.play(AssetSource('sounds/complete.mp3'));
  }

  Future<void> playTick() async {
    await _tickPlayer.stop();
    await _tickPlayer.play(AssetSource('sounds/wheel_tick.mp3'));
  }

  Future<void> playStop() async {
    await _fxPlayer.stop();
    await _fxPlayer.play(AssetSource('sounds/wheel_stop.mp3'));
  }
}
