import '../../models/lesson.dart';

/// Rythme de l'animation de l'écran 3 : l'affichage suit les vraies étapes du serveur,
/// mais n'en valide qu'une toutes les [minStep] au plus, pour rester lisible.
class StepPacer {
  StepPacer();

  static const minStep = Duration(milliseconds: 800);

  int _shown = 0;
  int _server = 0;

  int get shown => _shown;

  /// Toutes les étapes sont affichées comme terminées.
  bool get finished => _shown >= analysisSteps.length;

  void serverDone(int done) => _server = done.clamp(_server, analysisSteps.length);

  /// Appelé toutes les [minStep] : valide au plus une étape de plus. Rend `true` si
  /// l'affichage a changé.
  bool tick() {
    if (_shown >= _server) return false;
    _shown++;
    return true;
  }

  AnalysisStep stateOf(int index, {required bool failed}) {
    if (index < _shown) return AnalysisStep.done;
    if (index == _shown && !failed) return AnalysisStep.running;
    return AnalysisStep.pending;
  }
}
