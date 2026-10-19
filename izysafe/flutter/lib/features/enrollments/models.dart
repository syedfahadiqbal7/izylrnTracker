/// A school's enrollment request / active consent for one of the parent's children
/// (GET /enrollments). The parent grants or withdraws the three consents.
class ParentEnrollment {
  final String id;
  final String schoolName;
  final String childId;
  final String childName;
  final String? classGrade;
  final bool parentOptIn; // school may see the child
  final bool busOptIn; // bus tracking / assignment
  final bool locationOptIn; // live location sharing

  const ParentEnrollment({
    required this.id,
    required this.schoolName,
    required this.childId,
    required this.childName,
    required this.classGrade,
    required this.parentOptIn,
    required this.busOptIn,
    required this.locationOptIn,
  });

  bool get pending => !parentOptIn;

  factory ParentEnrollment.fromJson(Map<String, dynamic> j) => ParentEnrollment(
        id: j['id'] as String,
        schoolName: (j['school_name'] ?? '') as String,
        childId: j['child_id'] as String,
        childName: (j['child_name'] ?? '') as String,
        classGrade: j['class_grade'] as String?,
        parentOptIn: (j['parent_opt_in'] ?? false) as bool,
        busOptIn: (j['bus_opt_in'] ?? false) as bool,
        locationOptIn: (j['location_opt_in'] ?? false) as bool,
      );
}
