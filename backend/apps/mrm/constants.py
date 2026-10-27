"""Static option lists carried over from the legacy MRM system's Config."""

ACTIVITY_CODES = [
    'Airfield', 'Air Operations', 'Administration', 'Civil Military Operations', 'Command & Control',
    'Communications', 'Engineering', 'Force Protection', 'Ground Operations', 'HADR', 'Logistics',
    'Movement', 'Safety', 'Training', 'Others',
]

WEATHER_OPTIONS = [
    'Clear skies', 'Overcast / Cloudy', 'Rainy / Wet', 'Windy', 'Hot / Humid', 'Cold / Foggy',
]

LIGHTING_OPTIONS = [
    'Daylight', 'Dusk / Dawn', 'Nighttime (Fair)', 'Nighttime (Poor visibility)',
    'Adequate artificial lighting', 'Poor artificial lighting',
]

WORKSPACE_OPTIONS = [
    'Clean and organized', 'Congested / Crowded', 'Slippery / Uneven surface',
    'Hazardous materials present', 'Adequate ventilation', 'Poor ventilation', 'None',
]

OPERATIONAL_TEMPO_OPTIONS = [
    'Normal / Routine operations', 'High tempo / Increased workload', 'Emergency / Stressful environment',
]

IMSAFE_CHECKLIST = {
    'I': 'Illness - Am I free from any Illness',
    'M': 'Medication - Am I free from any impairing medication?',
    'S': 'Stress - Am I free from stress?',
    'A': 'Alcohol - Am I free from alcohol?',
    'F': 'Fatigue - Am I well rested and alert?',
    'E': 'Eating - Am I adequately nourished?',
}

ENVIRONMENT_FIELDS = ('weather', 'lighting', 'workspace', 'operational_tempo')

DEFAULT_MISSION_STATEMENT = 'Minimize risk to ALARP while maintaining operational effectiveness.'

PERSONNEL_ROLES = ['Mission Lead', 'Crew Member', 'Support']
