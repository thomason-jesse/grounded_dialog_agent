<?php

// Write to file.
// fn - the filename
// data - the data to put in the file
// err_msg - the error message to display if getting the file handle fails
function write_file($fn, $data, $err_msg) {
  $f = fopen($fn, 'w') or die($err_msg);
  fwrite($f, $data);
  fclose($f);
  chmod($fn, "a+r");
}

// Unlink the given file.
// fn - said filename
// err_msg = the error message to display if unlinking the filename fails
function delete_file($fn, $err_msg) {
	unlink($fn) or die($err_msg);
}

?>