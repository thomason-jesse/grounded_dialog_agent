<html>
<head>
<title>Command a Robot</title>

<!-- First include jquery js -->
<script src="//code.jquery.com/jquery-1.12.0.min.js"></script>
<script src="//code.jquery.com/jquery-migrate-1.2.1.min.js"></script>

<!-- Latest compiled and minified JavaScript -->
<script src="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/js/bootstrap.min.js" integrity="sha384-Tc5IQib027qvyjSMfHjOMaLkfuWVxZxUPnCJA7l2mCWNIpG9mGCD8wGNIcPD7Txa" crossorigin="anonymous"></script>

<!-- Latest compiled and minified CSS -->
<link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/css/bootstrap.min.css" integrity="sha384-BVYiiSIFeK1dGmJRAkycuHAHRg32OmUcww7on3RYdg4Va+PmSTsz/K68vbdEjh4u" crossorigin="anonymous">

<link rel="stylesheet" href="style.css">

<script type="text/javascript">
// Functions related to manipulating the actual interface and running the task.

// Show an error in the error div.
function show_error(e) {
  $('#err').show();
  $('#err_text').html(e);
}

// Enable the user text input.
function enable_user_text() {
  $('#user_input').prop("disabled", false);
  $('#user_say').prop("disabled", false);
}

// Disable user text input.
function disable_user_text() {
  $('#user_input').prop("disabled", true);
  $('#user_say').prop("disabled", true);
}

// Fill a panel with an image.
// type - either 'task' or 'interface'
// role - one of 'patient', 'recipient', 'source', or 'goal'
// atom - the ontological atom used to find the corresponding image for the panel
function fill_panel(type, role, atom) {
  if (role == "source" || role == "goal") {
    var rd = "maps/";
  } else if (role == "patient") {
    var rd = "objects/";
  } else if (role == "recipient") {
    // TODO: if we decide to use recipient, decide how
  }
  var fn = "images/" + rd + atom + ".png";
  var img = "<img src=\"" + fn + "\" class=\"panel_img\">";
  $('#' + type + '_' + role + '_panel').html(img);
}

// Remove all rows from the dialog table except the user input row.
function clear_dialog_table() {
  $("#dialog_table > tr").slice($('#myTable tr').length - 1).remove();
}

// Add a new row to the bottom of the dialog table.
// m - the string message to add
// u - true if message is from the user, false otherwise
function add_row_to_dialog_table(m, u) {
  var table = document.getElementById('dialog_table');
  var row = table.insertRow(table.rows.length - 1);
  var name_cell = row.insertCell(0);
  var msg_cell = row.insertCell(1);
  if (u) {
    name_cell.innerHTML = "YOU";
  } else {
    name_cell.innerHTML = "ROBOT";
  }
  msg_cell.innerHTML = m;
}

// Get user input text and send it to the agent.
function send_agent_user_input(d, uid) {
  disable_user_text();
  var m = $('#user_input').val();  // read the value
  $('#user_input').val('');  // clear user text
  add_row_to_dialog_table(m, true);  // add the user text to the dialog table history
  send_agent_string_message(d, uid, m);  // send user string message to the agent

  var finished = get_agent_message(d, uid);  // get a response from the agent
  if (!finished) {
    enable_user_text();
  }
  else {
    $('#finished_task_div').show();  // show button to advance to next task
  }
}

// Write a string message to disk for the server to pick up.
// d - the directory where messages live
// uid - the user id
// m - the string message to write to file
function send_agent_string_message(d, uid, m) {
  var fn = d + uid + ".smsgu.txt";
  var url = "manage_files.php?opt=write&fn=" + fn + "&m=" + encodeURIComponent(m);
  var success = http_get(url);
  if (success == "0") {
    show_error("Failed to write file '" + fn + "' with message contents '" + m + "'.<br>Attempt made with url '" + url + "'.");
  }
}

// Gets the next agent message and renders it on the dialog interface.
// d - the directory where messages live
// uid - the integer user id to read messages for
// return - true if the message was an action (dialog over), false otherwise
function get_agent_message(d, uid) {
  disable_user_text();  // disable user input from typing

  // Spin until agent message exists, process and delete it when it does.
  var got_message = false;
  var action_message = false;
  smsgs_url = d + uid + ".smsgs.txt";
  rmsgs_url = d + uid + ".rmsgs.txt";
  amsgs_url = d + uid + ".amsgs.txt";
  while (!got_message) {

    // Check for a string message, '[uid].smsgs.txt'
    if (url_exists(smsgs_url)) {
      var m = get_and_delete_file(smsgs_url);
      add_row_to_dialog_table(m, false);
      enable_user_text();  // TODO: need to detect whether we're pointing, later on
      got_message = true;
    }

    // Check for a referent message.
    else if (url_exists(rmsgs_url)) {
      var m = get_and_delete_file(rmsgs_url);
      // TODO: these contents need to be processed into string and panel
      add_row_to_dialog_table(m, false);
      enable_user_text();  // TODO: need to detect whether we're pointing, later on
      got_message = true;
    }

    // Check for an action message.
    else if (url_exists(amsgs_url)) {
      var contents = get_and_delete_file(amsgs_url);
      // TODO: these contents need to be processed into string and panel
      $('#action_text').html(m)
      got_message = true;
      action_message = true;
    }

    sleep(1000);  // sleep for one second before polling again
  }

  return action_message;
}

// Sample a task corresponding to the number and give it to the user.
function show_task(task_num, d, uid) {
  $('#next_task_div').hide();  // hide next task div
  clear_dialog_table();  // Clear the dialog history.

  // Sample a task of the matching number.
  if (task_num == 1) {
    var task_text = "<p>By commanding the robot, solve this problem:<br>The object shown below is at the X marked on the left map. The object belongs at the X marked on the right map.</p>";
    var patient = "oidx_28";
    var recipient = 0;
    var source = "3520";
    var goal = "3512";
  }
  else {
    show_error("Task number " + task_num + " unrecognized.");
  }

  // Render the task on the display.
  $('#task_text').html(task_text);
  if (patient) {
    fill_panel("task", "patient", patient);
  }
  if (recipient) {
    fill_panel("task", "recipient", recipient);
  }
  if (source) {
    fill_panel("task", "source", source);
  }
  if (goal) {
    fill_panel("task", "goal", goal);
  }

  // Get first message from robot and unhide display.
  $('#interaction_div').show();
  get_agent_message(d, uid);
}

// Functions related to server-side processing.

// Get the contents of the given url, then delete the underlying file.
// url - url to get from and then delete
// returns - the contents of the url page
function get_and_delete_file(url) {
  var contents = http_get(url);
  var del_url = "manage_files.php?opt=del&fn=" + encodeURIComponent(url);
  success = http_get(del_url);
  if (success == "0") {
    show_error("Failed to delete file '" + url + "' using url '" + del_url + "'.");
  }
  return contents;
}

// Get the contents of the given url.
// url - said url
// Implementation from: https://stackoverflow.com/questions/247483/http-get-request-in-javascript
function http_get(url)
{
    var xmlHttp = new XMLHttpRequest();
    xmlHttp.open("GET", url, false); // false for synchronous request
    xmlHttp.send(null);
    return xmlHttp.responseText;
}

// Check whether the given url returns a 404.
// url - the url to check
// returns bool
function url_exists(url) {
  var check_url = "manage_files.php?opt=exists&fn=" + encodeURIComponent(url);
  var exists = http_get(check_url);
  if (exists == "1") {
    return true;
  } else {
    return false;
  }
}

// Sleep for milliseconds.
// Implementation from: https://stackoverflow.com/questions/16873323/javascript-sleep-wait-before-continuing
function sleep(milliseconds) {
  var start = new Date().getTime();
  for (var i = 0; i < 1e7; i++) {
    if ((new Date().getTime() - start) > milliseconds){
      break;
    }
  }
}
</script>

</head>

<body>
<div id="container">

<div class="row" id="err" style="display:none;">
  <div class="col-md-1"></div>
  <div class="col-md-10" id="err_text"></div>
  <div class="col-md-1"></div>
</div>

<?php
require_once('functions.php');

$d = 'client/';

# This is a new landing, so we need to set up the task and call the Server to make an instance.
if (!isset($_POST['uid'])) {
  $uid = uniqid();

  # Write a new user file so the Server creates an Agent assigned to this uid.
  $fn = $d . $uid . '.newu.txt';
  write_file($fn, ' ', 'Could not create file to request new dialog agent.');

  # Show instructions.
  $inst = "<p>In this HIT, you will command a robot to perform several tasks. ";
  $inst .= "The robot is learning, and will ask you to reword your commands ";
  $inst .= "and help it better understand concepts. ";
  $inst .= "Use the chat box below to command the robot to complete the given task.</p><br/>";
  ?>
  <div class="row" id="inst_div">
    <div class="col-md-1"></div>
    <div class="col-md-10">
      <?php echo $inst;?>
      <form action="index.php" method="POST">
        <input type="hidden" name="uid" value="<?php echo $uid;?>">
        <input type="hidden" name="task_num" value="1">
        <input type="submit" class="btn" value="Okay">
      </form>
    </div>
    <div class="col-md-1"></div>
  </div>
  <?php
}

# This is a return landing, so load a task and show the interface.
else {

  $uid = $_POST['uid'];
  $task_num = $_POST['task_num'];

  # Show the goal and interface rows.
  ?>
  <div id="interaction_div" style="display:none;">
    <div class="row">
      <div class="col-md-1"></div>
      <div class="col-md-5" id="task_text"></div>
      <div class="col-md-5"></div>
      <div class="col-md-1"></div>
    </div>
    <div class="row">
      <div class="col-md-1"></div>
      <div class="col-md-5">
        <div class="row">
          <div class="col-md-1 patient_panel" id="task_patient_panel"></div>
          <div class="col-md-1 recipient_panel" id="task_recipient_panel"></div>
        </div>
        <div class="row">
          <div class="col-md-1 source_panel" id="task_source_panel"></div>
          <div class="col-md-1 goal_panel" id="task_goal_panel"></div>
        </div>
      </div>
      <div class="col-md-5" id="nearby_objects_div">
        Nearby Objects
      </div>
      <div class="col-md-1"></div>
    </div>

    <div class="row">
      <div class="col-md-1"></div>
      <div class="col-md-5">
        
        <table id="dialog_table"><tbody>
          <tr id="user_input_row"><td>YOU</td><td><input type="text" id="user_input"></td></tr>
        </tbody></table>
        <button class="btn" id="user_say" onclick="send_agent_user_input('<?php echo $d;?>', '<?php echo $uid;?>')">Say</button>

      </div>
      <div class="col-md-5">
        
      </div>
      <div class="col-md-1"></div>
    </div>
  </div>

  <div class="row" id="next_task_div">
    <div class="col-md-1"></div>
    <div class="col-md-10">
      <button class="btn" name="user_say" onclick="show_task(<?php echo $task_num;?>, '<?php echo $d;?>', '<?php echo $uid;?>')">Show next task</button>
    </div>
    <div class="col-md-1"></div>
  </div>

    <?php
}

# Show form to advance after completion/reading instructions.
?>
<div class="row" id="finished_task_div" style="display:none;">
  <div class="col-md-1"></div>
  <div class="col-md-10">
    <div id="action_text"></div>
    <form action="index.php" method="POST">
      <input type="hidden" name="uid" value="<?php echo $uid;?>">
      <input type="hidden" name="task_num" value="<?php echo $task_num;?>">
      <input type="submit" class="btn" value="Okay">
    </form>
  </div>
  <div class="col-md-1"></div>
</div>
<?php

# Show exit instructions.
# TODO: this should be it's own page that the user can navigate to only after finishing the task.
if (false) {
  $uid = $_POST['uid'];
  $mturk_code = $uid."_".substr(sha1("phm_salted_hash".$uid."rwhpidcwha_0"),0,13);
  ?>
  <div class="row">
    <div class="col-md-1"></div>
    <div class="col-md-10">
      <p>
        Thank you for your participation!</p>
      <p>Copy the code below, return to Mechanical Turk, and enter it to receive payment:<br/>
        <?php echo $mturk_code; ?>
      </p>
    </div>
    <div class="col-md-1"></div>
  </div>
  <?php
}
?>

</div>
</body>

</html>
