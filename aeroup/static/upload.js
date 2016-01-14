$(document).ready(function() {
  if ($('html').is('.ie6, .ie7, .ie8, .ie9')) {
    console.info("Your version of Internet Explorer is too old for drag-and-drop file uploading to work. Hiding. :(");
    $('.show-modern-world').hide();
    $('.show-ancient-world').show();
  }

  $('.animellipsis').each(function(index) {
    var ellipsis = $(this);
    // default is 3 dots (plus none)
    var totalDotModes = 4;
    if (ellipsis.attr('data-numdots')) {
        totalDotModes = parseInt(ellipsis.attr('data-numdots'), 10);
    } else {
        ellipsis.attr('data-numdots', totalDotModes.toString());
    }

    for (var i = 1; i < 4; i++) {
        ellipsis.append('<span class="dot dot' + i + '">.</span>');
    }
    ellipsis.attr('data-dot', '0');
  });

  window.setInterval(function(){
    $('.animellipsis').each(function(index){
      var ellipsis = $(this);
      ellipsis.attr('data-dot', parseInt(ellipsis.attr('data-dot'), 10) + 1);
      if (parseInt(ellipsis.attr('data-dot'), 10) > parseInt(ellipsis.attr('data-numdots'), 10) - 1) {
          ellipsis.attr('data-dot', '0');
      }

      var currentNum = parseInt(ellipsis.attr('data-dot'), 10);
      ellipsis.children('.dot').each(function(i) {
        var dot = $(this);
        var num = parseInt(dot.attr('class').replace(/dot/gi,'').replace(/\s/, ''), 10);
        if (num <= currentNum) {
            dot.show();
        } else {
            dot.hide();
        }
      });
    });
  }, 300);

  // Courtesy of @rem
  // http://html5demos.com/dnd-upload
  var holder = document.getElementById('file-upload-target'),
      tests = {
        filereader: typeof FileReader != 'undefined',
        dnd: 'draggable' in document.createElement('span'),
        formdata: !!window.FormData,
        progress: "upload" in new XMLHttpRequest
      },
      progress = document.getElementById('file-upload-progress'),
      fileupload = document.getElementById('upload');

  var readfiles = function(files) {
    var formData = tests.formdata ? new FormData() : null;
    for (var i = 0; i < files.length; i++) {
      if (tests.formdata) {
        formData.append('uploaded-file', files[i]);
      }

      var file = files[i];
      $(holder).hide();
      $('.ancient-world').hide();
      $(progress).parent('.progress').removeClass('hidden');
      $('#upload-in-progress').removeClass('hidden');
    }

    // now post a new XHR request
    if (tests.formdata) {
      var xhr = new XMLHttpRequest();
      xhr.open('POST', '/l/' + link_id);
      xhr.setRequestHeader('X-CSRFToken', csrftoken);

      xhr.onload = function() {
        $(progress).removeClass('progress-bar-striped active');
        $('#upload-in-progress').addClass('hidden');
        $('#upload-success').removeClass('hidden');

        var display_size = file.size;
        if (display_size < 1024) {
          display_size = display_size + 'B';
        } else if (display_size < 1024 * 1024) {
          display_size = ~~(display_size / 1024) + 'KB';
        } else {
          display_size = ~~(display_size / 1024 / 1024) + 'MB';
        }
        $('#upload-success').append('Sent ' + file.name + ' (' + display_size + ') to ' + person + '. Thanks! :)');
      };

      if (tests.progress) {
        xhr.upload.onprogress = function(event) {
          if (event.lengthComputable) {
            var complete = (event.loaded * 100 / event.total | 0);
            console.log("Sent " + event.loaded + " of " + event.total);
            $(progress).attr('aria-valuenow', complete);
            $(progress).css('width', complete + '%');
          }
        };
      }

      xhr.send(formData);
    }
  };

  if (tests.dnd) {
    holder.ondragover = function () { this.className = 'hover'; return false; };

    holder.ondragend = function () { this.className = ''; return false; };

    holder.ondrop = function (e) {
      this.className = '';
      e.preventDefault();
      readfiles(e.dataTransfer.files);
    };
  } else {
    fileupload.className = 'hidden';
    fileupload.querySelector('input').onchange = function() {
      readfiles(this.files);
    };
  }
});
