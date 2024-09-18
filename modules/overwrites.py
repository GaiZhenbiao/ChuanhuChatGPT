from __future__ import annotations

import gradio as gr
import multipart
from multipart.multipart import MultipartState, CR, LF, HYPHEN, COLON, lower_char, LOWER_A, LOWER_Z, SPACE, FLAG_PART_BOUNDARY, FLAG_LAST_BOUNDARY, join_bytes
from multipart.exceptions import MultipartParseError
from gradio.components.chatbot import ChatbotData, FileMessage
from gradio.data_classes import FileData
from gradio_client import utils as client_utils

from modules.utils import convert_bot_before_marked, convert_user_before_marked


def postprocess(
    self,
    value: list[list[str | tuple[str] | tuple[str, str] | None] | tuple] | None,
) -> ChatbotData:
    """
    Parameters:
        value: expects a `list[list[str | None | tuple]]`, i.e. a list of lists. The inner list should have 2 elements: the user message and the response message. The individual messages can be (1) strings in valid Markdown, (2) tuples if sending files: (a filepath or URL to a file, [optional string alt text]) -- if the file is image/video/audio, it is displayed in the Chatbot, or (3) None, in which case the message is not displayed.
    Returns:
        an object of type ChatbotData
    """
    if value is None:
        return ChatbotData(root=[])
    processed_messages = []
    for message_pair in value:
        if not isinstance(message_pair, (tuple, list)):
            raise TypeError(
                f"Expected a list of lists or list of tuples. Received: {message_pair}"
            )
        if len(message_pair) != 2:
            raise TypeError(
                f"Expected a list of lists of length 2 or list of tuples of length 2. Received: {message_pair}"
            )
        processed_messages.append(
            [
                self._postprocess_chat_messages(message_pair[0], "user"),
                self._postprocess_chat_messages(message_pair[1], "bot"),
            ]
        )
    return ChatbotData(root=processed_messages)


def postprocess_chat_messages(
    self, chat_message: str | tuple | list | None, role: str
) -> str | FileMessage | None:
    if chat_message is None:
        return None
    elif isinstance(chat_message, (tuple, list)):
        filepath = str(chat_message[0])

        mime_type = client_utils.get_mimetype(filepath)
        return FileMessage(
            file=FileData(path=filepath, mime_type=mime_type),
            alt_text=chat_message[1] if len(chat_message) > 1 else None,
        )
    elif isinstance(chat_message, str):
        # chat_message = inspect.cleandoc(chat_message)
        if role == "bot":
            # chat_message = inspect.cleandoc(chat_message)
            chat_message = convert_bot_before_marked(chat_message)
        elif role == "user":
            chat_message = convert_user_before_marked(chat_message)
        return chat_message
    else:
        raise ValueError(f"Invalid message for Chatbot component: {chat_message}")


def init_with_class_name_as_elem_classes(original_func):
    def wrapper(self, *args, **kwargs):
        if "elem_classes" in kwargs and isinstance(kwargs["elem_classes"], str):
            kwargs["elem_classes"] = [kwargs["elem_classes"]]
        else:
            kwargs["elem_classes"] = []

        kwargs["elem_classes"].append("gradio-" + self.__class__.__name__.lower())

        if kwargs.get("multiselect", False):
            kwargs["elem_classes"].append("multiselect")

        res = original_func(self, *args, **kwargs)
        return res

    return wrapper

def multipart_internal_write(self, data: bytes, length: int) -> int:
        # Get values from locals.
        boundary = self.boundary

        # Get our state, flags and index.  These are persisted between calls to
        # this function.
        state = self.state
        index = self.index
        flags = self.flags

        # Our index defaults to 0.
        i = 0

        # Set a mark.
        def set_mark(name):
            self.marks[name] = i

        # Remove a mark.
        def delete_mark(name, reset=False):
            self.marks.pop(name, None)

        # Helper function that makes calling a callback with data easier. The
        # 'remaining' parameter will callback from the marked value until the
        # end of the buffer, and reset the mark, instead of deleting it.  This
        # is used at the end of the function to call our callbacks with any
        # remaining data in this chunk.
        def data_callback(name, remaining=False):
            marked_index = self.marks.get(name)
            if marked_index is None:
                return

            # If we're getting remaining data, we ignore the current i value
            # and just call with the remaining data.
            if remaining:
                self.callback(name, data, marked_index, length)
                self.marks[name] = 0

            # Otherwise, we call it from the mark to the current byte we're
            # processing.
            else:
                self.callback(name, data, marked_index, i)
                self.marks.pop(name, None)

        # For each byte...
        # Add a counter for bytes consumed in the END state
        end_state_counter = 0
        while i < length:
            c = data[i]

            if state == MultipartState.START:
                # Skip leading newlines
                if c == CR or c == LF:
                    i += 1
                    self.logger.debug("Skipping leading CR/LF at %d", i)
                    continue

                # index is used as in index into our boundary.  Set to 0.
                index = 0

                # Move to the next state, but decrement i so that we re-process
                # this character.
                state = MultipartState.START_BOUNDARY
                i -= 1

            elif state == MultipartState.START_BOUNDARY:
                # Check to ensure that the last 2 characters in our boundary
                # are CRLF.
                if index == len(boundary) - 2:
                    if c != CR:
                        # Error!
                        msg = "Did not find CR at end of boundary (%d)" % (i,)
                        self.logger.warning(msg)
                        e = MultipartParseError(msg)
                        e.offset = i
                        raise e

                    index += 1

                elif index == len(boundary) - 2 + 1:
                    if c != LF:
                        msg = "Did not find LF at end of boundary (%d)" % (i,)
                        self.logger.warning(msg)
                        e = MultipartParseError(msg)
                        e.offset = i
                        raise e

                    # The index is now used for indexing into our boundary.
                    index = 0

                    # Callback for the start of a part.
                    self.callback("part_begin")

                    # Move to the next character and state.
                    state = MultipartState.HEADER_FIELD_START

                else:
                    # Check to ensure our boundary matches
                    if c != boundary[index + 2]:
                        msg = "Did not find boundary character %r at index " "%d" % (c, index + 2)
                        self.logger.warning(msg)
                        e = MultipartParseError(msg)
                        e.offset = i
                        raise e

                    # Increment index into boundary and continue.
                    index += 1

            elif state == MultipartState.HEADER_FIELD_START:
                # Mark the start of a header field here, reset the index, and
                # continue parsing our header field.
                index = 0

                # Set a mark of our header field.
                set_mark("header_field")

                # Move to parsing header fields.
                state = MultipartState.HEADER_FIELD
                i -= 1

            elif state == MultipartState.HEADER_FIELD:
                # If we've reached a CR at the beginning of a header, it means
                # that we've reached the second of 2 newlines, and so there are
                # no more headers to parse.
                if c == CR:
                    delete_mark("header_field")
                    state = MultipartState.HEADERS_ALMOST_DONE
                    i += 1
                    continue

                # Increment our index in the header.
                index += 1

                # Do nothing if we encounter a hyphen.
                if c == HYPHEN:
                    pass

                # If we've reached a colon, we're done with this header.
                elif c == COLON:
                    # A 0-length header is an error.
                    if index == 1:
                        msg = "Found 0-length header at %d" % (i,)
                        self.logger.warning(msg)
                        e = MultipartParseError(msg)
                        e.offset = i
                        raise e

                    # Call our callback with the header field.
                    data_callback("header_field")

                    # Move to parsing the header value.
                    state = MultipartState.HEADER_VALUE_START

                else:
                    # Lower-case this character, and ensure that it is in fact
                    # a valid letter.  If not, it's an error.
                    cl = lower_char(c)
                    if cl < LOWER_A or cl > LOWER_Z:
                        msg = "Found non-alphanumeric character %r in " "header at %d" % (c, i)
                        self.logger.warning(msg)
                        e = MultipartParseError(msg)
                        e.offset = i
                        raise e

            elif state == MultipartState.HEADER_VALUE_START:
                # Skip leading spaces.
                if c == SPACE:
                    i += 1
                    continue

                # Mark the start of the header value.
                set_mark("header_value")

                # Move to the header-value state, reprocessing this character.
                state = MultipartState.HEADER_VALUE
                i -= 1

            elif state == MultipartState.HEADER_VALUE:
                # If we've got a CR, we're nearly done our headers.  Otherwise,
                # we do nothing and just move past this character.
                if c == CR:
                    data_callback("header_value")
                    self.callback("header_end")
                    state = MultipartState.HEADER_VALUE_ALMOST_DONE

            elif state == MultipartState.HEADER_VALUE_ALMOST_DONE:
                # The last character should be a LF.  If not, it's an error.
                if c != LF:
                    msg = "Did not find LF character at end of header " "(found %r)" % (c,)
                    self.logger.warning(msg)
                    e = MultipartParseError(msg)
                    e.offset = i
                    raise e

                # Move back to the start of another header.  Note that if that
                # state detects ANOTHER newline, it'll trigger the end of our
                # headers.
                state = MultipartState.HEADER_FIELD_START

            elif state == MultipartState.HEADERS_ALMOST_DONE:
                # We're almost done our headers.  This is reached when we parse
                # a CR at the beginning of a header, so our next character
                # should be a LF, or it's an error.
                if c != LF:
                    msg = f"Did not find LF at end of headers (found {c!r})"
                    self.logger.warning(msg)
                    e = MultipartParseError(msg)
                    e.offset = i
                    raise e

                self.callback("headers_finished")
                state = MultipartState.PART_DATA_START

            elif state == MultipartState.PART_DATA_START:
                # Mark the start of our part data.
                set_mark("part_data")

                # Start processing part data, including this character.
                state = MultipartState.PART_DATA
                i -= 1

            elif state == MultipartState.PART_DATA:
                # We're processing our part data right now.  During this, we
                # need to efficiently search for our boundary, since any data
                # on any number of lines can be a part of the current data.
                # We use the Boyer-Moore-Horspool algorithm to efficiently
                # search through the remainder of the buffer looking for our
                # boundary.

                # Save the current value of our index.  We use this in case we
                # find part of a boundary, but it doesn't match fully.
                prev_index = index

                # Set up variables.
                boundary_length = len(boundary)
                boundary_end = boundary_length - 1
                data_length = length
                boundary_chars = self.boundary_chars

                # If our index is 0, we're starting a new part, so start our
                # search.
                if index == 0:
                    # Search forward until we either hit the end of our buffer,
                    # or reach a character that's in our boundary.
                    i += boundary_end
                    while i < data_length - 1 and data[i] not in boundary_chars:
                        i += boundary_length

                    # Reset i back the length of our boundary, which is the
                    # earliest possible location that could be our match (i.e.
                    # if we've just broken out of our loop since we saw the
                    # last character in our boundary)
                    i -= boundary_end
                    c = data[i]

                # Now, we have a couple of cases here.  If our index is before
                # the end of the boundary...
                if index < boundary_length:
                    # If the character matches...
                    if boundary[index] == c:
                        # If we found a match for our boundary, we send the
                        # existing data.
                        if index == 0:
                            data_callback("part_data")

                        # The current character matches, so continue!
                        index += 1
                    else:
                        index = 0

                # Our index is equal to the length of our boundary!
                elif index == boundary_length:
                    # First we increment it.
                    index += 1

                    # Now, if we've reached a newline, we need to set this as
                    # the potential end of our boundary.
                    if c == CR:
                        flags |= FLAG_PART_BOUNDARY

                    # Otherwise, if this is a hyphen, we might be at the last
                    # of all boundaries.
                    elif c == HYPHEN:
                        flags |= FLAG_LAST_BOUNDARY

                    # Otherwise, we reset our index, since this isn't either a
                    # newline or a hyphen.
                    else:
                        index = 0

                # Our index is right after the part boundary, which should be
                # a LF.
                elif index == boundary_length + 1:
                    # If we're at a part boundary (i.e. we've seen a CR
                    # character already)...
                    if flags & FLAG_PART_BOUNDARY:
                        # We need a LF character next.
                        if c == LF:
                            # Unset the part boundary flag.
                            flags &= ~FLAG_PART_BOUNDARY

                            # Callback indicating that we've reached the end of
                            # a part, and are starting a new one.
                            self.callback("part_end")
                            self.callback("part_begin")

                            # Move to parsing new headers.
                            index = 0
                            state = MultipartState.HEADER_FIELD_START
                            i += 1
                            continue

                        # We didn't find an LF character, so no match.  Reset
                        # our index and clear our flag.
                        index = 0
                        flags &= ~FLAG_PART_BOUNDARY

                    # Otherwise, if we're at the last boundary (i.e. we've
                    # seen a hyphen already)...
                    elif flags & FLAG_LAST_BOUNDARY:
                        # We need a second hyphen here.
                        if c == HYPHEN:
                            # Callback to end the current part, and then the
                            # message.
                            self.callback("part_end")
                            self.callback("end")
                            state = MultipartState.END
                        else:
                            # No match, so reset index.
                            index = 0

                # If we have an index, we need to keep this byte for later, in
                # case we can't match the full boundary.
                if index > 0:
                    self.lookbehind[index - 1] = c

                # Otherwise, our index is 0.  If the previous index is not, it
                # means we reset something, and we need to take the data we
                # thought was part of our boundary and send it along as actual
                # data.
                elif prev_index > 0:
                    # Callback to write the saved data.
                    lb_data = join_bytes(self.lookbehind)
                    self.callback("part_data", lb_data, 0, prev_index)

                    # Overwrite our previous index.
                    prev_index = 0

                    # Re-set our mark for part data.
                    set_mark("part_data")

                    # Re-consider the current character, since this could be
                    # the start of the boundary itself.
                    i -= 1

            elif state == MultipartState.END:
                # Count bytes consumed in the end state
                if c not in (CR, LF):
                    self.logger.warning("Consuming a byte '0x%x' in the end state", c)
                    end_state_counter += 1

                    # It seems that raising an error is the best way to stop the parser
                    # Raise an error when consuming more than 10 bytes in the end state
                    # Raising an error immediately seems fine, but to be cautious, let’s raise an error when more than 10 bytes are consumed
                    if end_state_counter > 10:
                        raise MultipartParseError("Consumed more than 10 bytes in the end state")
                else:
                    # Reset the counter for CR or LF
                    end_state_counter = 0

            else:  # pragma: no cover (error case)
                # We got into a strange state somehow!  Just stop processing.
                msg = "Reached an unknown state %d at %d" % (state, i)
                self.logger.warning(msg)
                e = MultipartParseError(msg)
                e.offset = i
                raise e

            # Move to the next byte.
            i += 1

        # We call our callbacks with any remaining data.  Note that we pass
        # the 'remaining' flag, which sets the mark back to 0 instead of
        # deleting it, if it's found.  This is because, if the mark is found
        # at this point, we assume that there's data for one of these things
        # that has been parsed, but not yet emitted.  And, as such, it implies
        # that we haven't yet reached the end of this 'thing'.  So, by setting
        # the mark to 0, we cause any data callbacks that take place in future
        # calls to this function to start from the beginning of that buffer.
        data_callback("header_field", True)
        data_callback("header_value", True)
        data_callback("part_data", True)

        # Save values to locals.
        self.state = state
        self.index = index
        self.flags = flags

        # Return our data length to indicate no errors, and that we processed
        # all of it.
        return length

def patch_gradio():
    gr.components.Component.__init__ = init_with_class_name_as_elem_classes(
        gr.components.Component.__init__
    )

    gr.blocks.BlockContext.__init__ = init_with_class_name_as_elem_classes(
        gr.blocks.BlockContext.__init__
    )

    gr.Chatbot._postprocess_chat_messages = postprocess_chat_messages
    gr.Chatbot.postprocess = postprocess
    multipart.MultipartParser._internal_write = multipart_internal_write
