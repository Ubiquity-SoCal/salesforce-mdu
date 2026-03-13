Map<String, List<TrackerController.PicklistOption>> result = TrackerController.getPicklistValues('Opportunity');
System.debug('Keys: ' + result.keySet());
for (String key : result.keySet()) {
    List<TrackerController.PicklistOption> opts = result.get(key);
    System.debug(key + ': ' + opts.size() + ' values');
    if (opts.size() > 0) {
        System.debug('  First: ' + opts[0].label + ' / ' + opts[0].value);
    }
}
