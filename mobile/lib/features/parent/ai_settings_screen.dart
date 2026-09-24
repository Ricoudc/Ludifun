import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/link_opener.dart';
import '../../core/session.dart';
import '../../models/ai.dart';
import 'goals_screen.dart' show showSnack;

final aiSettingsProvider = FutureProvider.autoDispose<AiSettings>(
  (ref) => ref.watch(apiProvider).aiSettings(),
);

/// « Intelligence artificielle » : l'IA qui lit les photos et crée les jeux, pour toute la
/// famille. Ollama (sur le PC de la maison) est proposé en premier : gratuit, rien ne sort.
class AiSettingsScreen extends ConsumerWidget {
  const AiSettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
    appBar: AppBar(
      leading: BackButton(onPressed: () => context.go(Routes.parentHome)),
      title: const Text('Intelligence artificielle'),
    ),
    body: switch (ref.watch(aiSettingsProvider)) {
      AsyncData(:final value) => _AiForm(value, key: ValueKey(value.family?.provider)),
      AsyncError(:final error) => CenteredBody(
        children: [ErrorMessage(error is ApiException ? error.message : ApiException.unexpected)],
      ),
      _ => const Center(child: CircularProgressIndicator()),
    },
  );
}

class _AiForm extends ConsumerStatefulWidget {
  const _AiForm(this.settings, {super.key});

  final AiSettings settings;

  @override
  ConsumerState<_AiForm> createState() => _AiFormState();
}

class _AiFormState extends ConsumerState<_AiForm> {
  late String _code;
  final _url = TextEditingController();
  final _key = TextEditingController();
  final _model = TextEditingController();
  AiCheck? _check;
  bool _busy = false;

  AiSettings get _settings => widget.settings;
  AiProvider get _provider => _settings.provider(_code)!;
  FamilyAi? get _saved => _settings.family?.provider == _code ? _settings.family : null;

  @override
  void initState() {
    super.initState();
    final recommended = _settings.providers.firstWhere(
      (p) => p.recommended && p.available,
      orElse: () => _settings.providers.firstWhere((p) => p.available),
    );
    _select(_settings.family?.provider ?? recommended.code);
  }

  @override
  void dispose() {
    _url.dispose();
    _key.dispose();
    _model.dispose();
    super.dispose();
  }

  void _select(String code) {
    _code = code;
    _check = null;
    _key.clear();
    _url.text = _saved?.baseUrl ?? _provider.defaultUrl ?? '';
    _model.text = _saved?.model ?? '';
  }

  String? _text(TextEditingController c) => c.text.trim().isEmpty ? null : c.text.trim();

  Future<void> _run(Future<void> Function() action) async {
    setState(() => _busy = true);
    try {
      await action();
    } on ApiException catch (error) {
      if (mounted) showSnack(context, error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _test() => _run(() async {
    final check = await ref
        .read(apiProvider)
        .testAi(_code, model: _text(_model), baseUrl: _text(_url), apiKey: _text(_key));
    setState(() => _check = check);
  });

  Future<void> _save() => _run(() async {
    await ref
        .read(apiProvider)
        .saveAiSettings(_code, model: _text(_model), baseUrl: _text(_url), apiKey: _text(_key));
    ref.invalidate(aiSettingsProvider);
    if (mounted) {
      showSnack(context, 'IA enregistrée : elle servira dès la prochaine leçon.');
    }
  });

  Future<void> _reset() => _run(() async {
    await ref.read(apiProvider).resetAiSettings();
    ref.invalidate(aiSettingsProvider);
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context).textTheme;
    final family = _settings.family;
    final current = family == null
        ? '${_settings.labelOf(_settings.serverProvider)} (réglage du serveur)'
        : '${_settings.labelOf(family.provider)}${family.model == null ? '' : ' · ${family.model}'}';
    final p = _provider;
    return CenteredBody(
      top: true,
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Text(
              'IA utilisée en ce moment : $current',
              style: const TextStyle(fontSize: 17),
            ),
          ),
        ),
        const SizedBox(height: 16),
        Text('Quelle IA lit les photos et crée les jeux ?', style: theme.titleMedium),
        const SizedBox(height: 4),
        RadioGroup<String>(
          groupValue: _code,
          onChanged: (code) => setState(() => _select(code!)),
          child: Column(
            children: [
              for (final provider in _settings.providers)
                if (provider.available)
                  RadioListTile<String>(
                    value: provider.code,
                    contentPadding: EdgeInsets.zero,
                    title: Text(
                      provider.recommended ? '${provider.label} · conseillé' : provider.label,
                      style: TextStyle(
                        fontWeight: provider.recommended ? FontWeight.w700 : FontWeight.w500,
                      ),
                    ),
                    subtitle: provider.code == _code && provider.note.isNotEmpty
                        ? Text(provider.note)
                        : null,
                  ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        if (p.customUrl) ...[
          TextField(
            controller: _url,
            keyboardType: TextInputType.url,
            decoration: InputDecoration(
              labelText: p.code == 'ollama' ? 'Adresse d\'Ollama' : 'Adresse de l\'API',
              helperText: p.code == 'ollama'
                  ? 'Laissez l\'adresse proposée si Ollama tourne sur le PC du serveur.'
                  : 'Par exemple https://<ressource>.openai.azure.com/openai/v1',
            ),
          ),
          const SizedBox(height: 12),
        ],
        if (p.asksKey) ...[
          TextField(
            controller: _key,
            obscureText: true,
            autocorrect: false,
            enableSuggestions: false,
            decoration: InputDecoration(
              labelText: p.needsKey ? 'Clé d\'API' : 'Clé d\'API (si le service en demande une)',
              helperText: _saved?.keyHint == null
                  ? null
                  : 'Clé enregistrée ${_saved!.keyHint} : laissez vide pour la garder.',
            ),
          ),
          if (p.keyUrl.isNotEmpty)
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: () => ref.read(linkOpenerProvider).open(Uri.parse(p.keyUrl)),
                icon: const Icon(Icons.open_in_new, size: 18),
                label: const Text('Créer une clé'),
              ),
            ),
          const SizedBox(height: 12),
        ] else if (p.code == 'ollama' && p.keyUrl.isNotEmpty)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () => ref.read(linkOpenerProvider).open(Uri.parse(p.keyUrl)),
              icon: const Icon(Icons.open_in_new, size: 18),
              label: const Text('Installer Ollama'),
            ),
          ),
        if (p.code != 'fake')
          TextField(
            controller: _model,
            autocorrect: false,
            decoration: InputDecoration(
              labelText: p.defaultModel == null ? 'Modèle' : 'Modèle (facultatif)',
              helperText: p.defaultModel == null
                  ? 'Il doit savoir lire les images.'
                  : 'Vide : ${p.defaultModel} (conseillé)',
            ),
          ),
        if (_check case final check?) ...[
          const SizedBox(height: 16),
          Text(
            '${check.ok ? '✅' : '⚠️'} ${check.message}',
            style: TextStyle(
              fontSize: 16,
              color: check.ok ? LudiColors.mastered : LudiColors.notMastered,
            ),
          ),
          if (check.models.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text('Modèles disponibles (touchez pour choisir) :', style: theme.bodyMedium),
            const SizedBox(height: 4),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final model in check.models.take(30))
                  ActionChip(
                    label: Text(model),
                    onPressed: () => setState(() => _model.text = model),
                  ),
              ],
            ),
          ],
        ],
        const SizedBox(height: 20),
        if (p.code != 'fake')
          OutlinedButton.icon(
            onPressed: _busy ? null : _test,
            icon: const Icon(Icons.wifi_tethering),
            label: const Text('Tester la connexion'),
          ),
        const SizedBox(height: 12),
        FilledButton(onPressed: _busy ? null : _save, child: const Text('Enregistrer')),
        if (family != null) ...[
          const SizedBox(height: 12),
          TextButton(
            onPressed: _busy ? null : _reset,
            child: const Text('Revenir à l\'IA du serveur'),
          ),
        ],
      ],
    );
  }
}
