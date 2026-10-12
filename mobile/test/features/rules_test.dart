import 'package:flutter_test/flutter_test.dart';
import 'package:ludifun/app/format.dart';
import 'package:ludifun/features/analysis/step_pacer.dart';
import 'package:ludifun/features/capture/image_compressor.dart';
import 'package:ludifun/models/lesson.dart';

void main() {
  test('compression : côté long ramené à 2000 px, jamais agrandi', () {
    expect(targetSize(3000, 4000), (1500, 2000));
    expect(targetSize(4032, 3024), (2000, 1500));
    expect(targetSize(1200, 900), (1200, 900));
  });

  group('prochaine révision (écran 1)', () {
    final wednesday = DateTime(2026, 9, 23, 18);
    LessonSummary lesson({DateTime? next, bool due = false, bool mastered = false}) =>
        LessonSummary(
          id: 'l1',
          status: LessonStatus.ready,
          createdAt: wednesday,
          nextReviewAt: next,
          due: due,
          mastered: mastered,
        );

    test('jour de la semaine, demain, date', () {
      expect(dayLabel(DateTime(2026, 9, 23, 20), wednesday), 'aujourd\'hui');
      expect(dayLabel(DateTime(2026, 9, 24, 8), wednesday), 'demain');
      expect(dayLabel(DateTime(2026, 9, 25, 8), wednesday), 'vendredi');
      expect(dayLabel(DateTime(2026, 9, 29, 8), wednesday), 'mardi');
      expect(dayLabel(DateTime(2026, 10, 1, 8), wednesday), 'le 1er octobre');
      expect(dayLabel(DateTime(2026, 10, 7, 8), wednesday), 'le 7 octobre');
    });

    test('libellés', () {
      expect(reviewLabel(lesson(due: true, mastered: true), wednesday), 'à revoir aujourd\'hui 🔄');
      expect(reviewLabel(lesson(mastered: true), wednesday), 'maîtrisée ✓');
      expect(reviewLabel(lesson(next: DateTime(2026, 9, 24, 9)), wednesday), 'à revoir demain');
      expect(reviewLabel(lesson(), wednesday), 'à réviser');
    });
  });

  test('analyse : une étape validée au plus à chaque pas de 800 ms', () {
    final pacer = StepPacer();
    expect(pacer.stateOf(0, failed: false), AnalysisStep.running);
    pacer.serverDone(3); // le serveur a déjà tout fini
    expect([pacer.tick(), pacer.shown], [true, 1]);
    expect(pacer.stateOf(0, failed: false), AnalysisStep.done);
    expect(pacer.stateOf(1, failed: false), AnalysisStep.running);
    expect(pacer.stateOf(2, failed: false), AnalysisStep.pending);
    pacer
      ..tick()
      ..tick();
    expect(pacer.finished, isTrue);
    expect(pacer.tick(), isFalse);

    final failed = StepPacer()..serverDone(1);
    failed.tick();
    expect(failed.stateOf(1, failed: true), AnalysisStep.pending); // plus de sablier
    failed.serverDone(0); // jamais de retour en arrière
    expect(failed.shown, 1);
  });
}
