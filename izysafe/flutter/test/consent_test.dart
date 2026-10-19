import 'package:flutter_test/flutter_test.dart';
import 'package:izysafe_parent/features/enrollments/models.dart';

void main() {
  group('ParentEnrollment (consent wizard source model)', () {
    test('parses a pending enrollment envelope row', () {
      final e = ParentEnrollment.fromJson({
        'id': 'enr-1',
        'school_name': 'Panel Demo School',
        'child_id': 'child-1',
        'child_name': 'Aarav',
        'class_grade': 'Grade 3',
        'parent_opt_in': false,
        'bus_opt_in': false,
        'location_opt_in': false,
      });
      expect(e.id, 'enr-1');
      expect(e.schoolName, 'Panel Demo School');
      expect(e.childName, 'Aarav');
      expect(e.classGrade, 'Grade 3');
      expect(e.parentOptIn, isFalse);
      // Not approved yet → the list launches the guided wizard.
      expect(e.pending, isTrue);
    });

    test('an approved enrollment is not pending', () {
      final e = ParentEnrollment.fromJson({
        'id': 'enr-2',
        'school_name': 'Panel Demo School',
        'child_id': 'child-2',
        'child_name': 'Zoya',
        'class_grade': null,
        'parent_opt_in': true,
        'bus_opt_in': true,
        'location_opt_in': false,
      });
      expect(e.pending, isFalse);
      expect(e.classGrade, isNull);
      expect(e.busOptIn, isTrue);
      expect(e.locationOptIn, isFalse);
    });

    test('defaults missing consent flags to false', () {
      final e = ParentEnrollment.fromJson({
        'id': 'enr-3',
        'child_id': 'child-3',
      });
      expect(e.schoolName, '');
      expect(e.childName, '');
      expect(e.parentOptIn, isFalse);
      expect(e.busOptIn, isFalse);
      expect(e.locationOptIn, isFalse);
      expect(e.pending, isTrue);
    });
  });
}
