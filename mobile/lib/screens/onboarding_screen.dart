import 'package:flutter/material.dart';

import '../api/models.dart';
import '../main.dart';

const grades = ['CP', 'CE1', 'CE2', 'CM1', 'CM2', '6e', '5e', '4e', '3e'];

class OnboardingScreen extends StatefulWidget {
  final ValueChanged<Child> onCreated;
  const OnboardingScreen({super.key, required this.onCreated});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final _name = TextEditingController();
  String _grade = 'CM1';
  bool _busy = false;

  Future<void> _submit() async {
    if (_name.text.trim().isEmpty) return;
    setState(() => _busy = true);
    try {
      widget.onCreated(await api.createChild(_name.text.trim(), _grade));
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 32),
              const Text('👋 Bienvenue !', style: TextStyle(fontSize: 32, fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              const Text('Photographie ta leçon, je t\'aide à la réviser en jouant.'),
              const SizedBox(height: 32),
              TextField(
                controller: _name,
                decoration: const InputDecoration(labelText: 'Ton prénom ou un pseudo', border: OutlineInputBorder()),
              ),
              const SizedBox(height: 16),
              const Text('Ta classe'),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final g in grades)
                    ChoiceChip(label: Text(g), selected: _grade == g, onSelected: (_) => setState(() => _grade = g)),
                ],
              ),
              const Spacer(),
              FilledButton(
                onPressed: _busy ? null : _submit,
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: _busy ? const CircularProgressIndicator() : const Text('C\'est parti !'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
