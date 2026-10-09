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

  test('Les Fondamentaux et Maître Lucas : une page de leçon, seulement sur leur site', () {
    Map<String, Object?> json(String provider, String kind, String url) => {
      'id': 'r1',
      'provider': provider,
      'kind': kind,
      'title': 'Les fractions',
      'url': url,
      'licence': 'Maître Lucas (consultation seulement, rien n\'est copié)',
    };
    final lucas = LessonResource.tryParse(
      json('maitrelucas', 'lesson', 'https://www.maitrelucas.fr/fractions/'),
    );
    expect(lucas?.provider, ResourceProvider.maitrelucas);
    expect(lucas?.kind.label, 'Leçon');
    expect(
      LessonResource.tryParse(json('maitrelucas', 'lesson', 'https://www.youtube.com/watch?v=x')),
      isNull,
    );
    expect(
      LessonResource.tryParse(
        json('fondamentaux', 'video', 'https://www.reseau-canope.fr/lesfondamentaux/x.html'),
      )?.provider.label,
      'Les Fondamentaux (Canopé)',
    );
  });

  test('Calcul@TICE et Sésamath : un jeu et une page de manuel, sur leur site', () {
    final game = LessonResource.tryParse({
      'id': 'r1',
      'provider': 'calculatice',
      'kind': 'game',
      'title': 'La table de multiplication',
      'url': 'https://calculatice.ac-lille.fr/spip.php?article57',
      'licence': 'Calcul@TICE',
    });
    expect(game?.kind.label, 'Jeu');
    expect(
      ResourceProvider.sesamath.allows(Uri.parse('https://manuel.sesamath.net/numerique/')),
      isTrue,
    );
    expect(ResourceProvider.calculatice.allows(Uri.parse('https://ac-lille.fr/')), isFalse);
  });
}
