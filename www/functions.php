<?php

// Read a file.
// fn - the filename
// returns a string of file contents or false
function read_file($fn) {
	$cmd = "cat " . $fn;
	$d = shell_exec($cmd);
	if (!$d || strcmp("cat:", substr($d, 0, 4)) == 0) {
		return false;
	} else {
		return $d;
	}
}

// Write to file.
// fn - the filename
// data - the data to put in the file
// err_msg - the error message to display if getting the file handle fails
function write_file($fn, $data, $err_msg) {
	$f = fopen($fn, 'w') or die($err_msg);
	fwrite($f, $data);
	fclose($f);
}

// Unlink the given file.
// fn - said filename
// err_msg = the error message to display if unlinking the filename fails
function delete_file($fn, $err_msg) {
	unlink($fn) or die($err_msg);
}

// Get the active train set from the fold using the CoRL folds.
// f - the fold
// returns an array of oidxs
function get_active_train_set($f) {
	if ($f == 0) {
		return array("oidx_10", "oidx_3", "oidx_27", "oidx_7", "oidx_18", "oidx_2", "oidx_20", "oidx_17");
	} elseif ($f == 1) {
		return array("oidx_5", "oidx_14", "oidx_8", "oidx_15", "oidx_1", "oidx_30", "oidx_29", "oidx_31");
	} elseif ($f == 2) {
		return array("oidx_21", "oidx_24", "oidx_19", "oidx_23", "oidx_16", "oidx_0", "oidx_4", "oidx_9");
	} elseif ($f == 3) {
		return array();
	}
}

// returns 1, 2, or 3 uniformly at random
function draw_task_num() {
	return rand(1, 3);
}

// Draw a task given a task number and a setting.
// task_num - either 1, 2, or 3
// setting - either init, train, or test
function draw_task($task_num, $setting) {

	// Convert the task number into the task type.
	if ($task_num == 1) {
		$task_name = "walking";
	} elseif ($task_num == 2) {
		$task_name = "delivery";
	} elseif ($task_num == 3) {
		$task_name = "relocation";
	} else {
		return false;
	}

	// Decode the appropriate json file to see all tasks.
	$fn = "tasks/" . $task_name . "_" . $setting . ".json";
	$s = read_file($fn);
	if (!$s) {
		return false;
	}
	$d = json_decode($s, true);

	// Draw from these tasks uniformly at random.
	$key = array_rand($d);
	return $d[$key];
}

?>