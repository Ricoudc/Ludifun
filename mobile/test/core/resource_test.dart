import 'package:flutter_test/flutter_test.dart';
import 'package:ludifun/models/resource.dart';

void main() {
  test('score MathALÉA : message actuel, ancien message, le reste est ignoré', () {
    String? read(String message) => scoreFromMessage(message)?.toString();
    expect(
      read(
        '{"action":"mathalea:score","resultsByExercice":['
        '{"numberOfPoints":3,"numberOfQuestions":5},{"numberOfPoints":2,"numberOfQuestions":2}]}',
      ),
      '5/7',
    );
    expect(read('{"nbBonnesReponses":4,"nbMauvaisesReponses":1}'), '4/5');
    for (final other in [
      'pas du JSON',
      '"texte"',
      '{"action":"mathalea:score","resultsByExercice":[]}',
      '{"action":"mathalea:score","resultsByExercice":[{"numberOfPoints":6,"numberOfQuestions":5}]}',
      '{"nbBonnesReponses":-1}',
      '{"type":"resize","height":300}',
    ]) {
      expect(read(other), isNull, reason: other);
    }
  });

  test('la visionneuse reste sur le site du fournisseur, en https', () {
    expect(ResourceProvider.mathalea.allows(Uri.parse('https://coopmaths.fr/alea/')), isTrue);
    expect(ResourceProvider.lumni.allows(Uri.parse('https://www.lumni.fr/video/x')), isTrue);
    expect(ResourceProvider.lumni.allows(Uri.parse('http://www.lumni.fr/video/x')), isFalse);
    expect(ResourceProvider.vikidia.allows(Uri.parse('https://vikidia.org.evil.fr/')), isFalse);
    expect(ResourceProvider.vikidia.allows(Uri.parse('https://www.lumni.fr/')), isFalse);
  });
}
