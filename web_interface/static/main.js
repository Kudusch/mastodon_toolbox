"use strict";

function document_ready(callback) {
    // in case the document is already rendered
    if (document.readyState != 'loading') callback();
    // modern browsers
    else if (document.addEventListener) document.addEventListener('DOMContentLoaded', callback);
    // IE <= 8
    else document.attachEvent('onreadystatechange', function() {
        if (document.readyState == 'complete') callback();
    });
}

document_ready(function() {
    $("#result").html("<p>There are " + Object.keys(toots).length + " toots.</p>");
});